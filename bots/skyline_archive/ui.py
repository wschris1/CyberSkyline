"""Owner-bound Discord components, staged menus and permission-aware result pages."""

import json
import re
from collections import Counter
from datetime import datetime
from urllib.parse import quote

import discord

from .core import ArchiveError, skyline_url
from .scanner import matches
from .discord_archive import jump


class OwnerView(discord.ui.View):
    def __init__(self, client, owner, timeout=600):
        super().__init__(timeout=timeout)
        self.client,self.owner=client,owner

    async def interaction_check(self, interaction):
        allowed=(interaction.guild_id==self.client.settings.guild_id and
                 interaction.user.id==self.owner and interaction.user.id in self.client.settings.owners)
        if not allowed:
            await interaction.response.send_message('This control belongs to its authorized owner.',ephemeral=True)
        return allowed

    async def on_error(self, interaction, error, item):
        message=str(error) if isinstance(error,ArchiveError) else 'The action failed. Check permissions and try again.'
        if interaction.response.is_done():
            await interaction.followup.send(message[:1900],ephemeral=True)
        else:
            await interaction.response.send_message(message[:1900],ephemeral=True)

    def button(self,label,callback,*,row=1,disabled=False,style=discord.ButtonStyle.secondary):
        b=discord.ui.Button(label=label,row=row,disabled=disabled,style=style)
        b.callback=callback
        self.add_item(b)


def diagnostic_text(value, settings, limit=600):
    """Keep logs, signed URLs, and credentials out of Discord diagnostics."""
    text = str(value or '')
    for name in ('discord_token','github_token','openai_api_key'):
        secret = getattr(settings,name,'')
        if secret:
            text = text.replace(secret,'[redacted]')
    text = re.sub(r'https?://[^\s<>]+','[URL omitted]',text,flags=re.I)
    text = re.sub(r'(?im)\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=][^\r\n]*',
                  '[header redacted]',text)
    text = re.sub(r'(?i)\b(?:[\w-]*(?:token|secret|password)|api[_-]?key)\b\s*[:=]\s*[^\s,;]+',
                  '[credential redacted]',text)
    text = re.sub(r'(?i)\bBearer\s+\S+','[credential redacted]',text)
    text = ''.join(c for c in text if c in '\n\t' or ord(c)>=32)
    return discord.utils.escape_mentions(discord.utils.escape_markdown(text))[:limit]


def failure_help(error):
    text = str(error or '').casefold()
    if 'interactive conversation' in text:
        return ('Interactive challenge', 'Later questions require replies on Cyber Skyline. Automatic retries cannot reveal them; no answers were submitted.')
    if any(s in text for s in ('timed out','navigation or page evaluation','network failure')):
        return ('Page/network error', 'Open the source page to check availability, then retry failed items.')
    if any(s in text for s in ('expected content','page layout','incomplete rows','missing title')):
        return ('Unsupported or incomplete page', 'Open the source page. If it loads normally, its question layout needs an extractor update.')
    if 'cache' in text or 'download limit' in text:
        return ('File/cache limit', 'Check file size, free disk space and the file/cache budgets in /skyline settings.')
    if 'upload' in text or 'files need retry' in text:
        return ('Attachment problem', 'Check the file statuses below and /skyline health before retrying. Existing question posts are preserved.')
    if any(s in text for s in ('forbidden','permission','category is full')):
        return ('Discord destination', 'Check destination permissions and category capacity in /skyline settings, then retry.')
    if 'login' in text or 'session' in text:
        return ('Source access/session', 'Check /skyline health. If login expired, refresh the saved login and run /skyline session recheck.')
    return ('Scan error', 'Check the saved reason and /skyline health before retrying; a retry cannot fix every cause.')


class FailuresView(OwnerView):
    def __init__(self,client,owner,scan_id=None):
        super().__init__(client,owner)
        self.scan_id,self.page=scan_id,0
        async def previous(i):
            self.page=max(0,self.page-1)
            await i.response.edit_message(content=self.render(),view=self)
        async def following(i):
            self.page+=1
            await i.response.edit_message(content=self.render(),view=self)
        async def refresh(i):
            await i.response.edit_message(content=self.render(),view=self)
        self.button('Previous',previous)
        self.button('Next',following)
        self.button('Refresh',refresh)

    def render(self):
        scan,rows=self.client.jobs.failures(self.scan_id)
        self.children[0].disabled=self.page<=0
        self.children[1].disabled=not rows or self.page>=len(rows)-1
        if not scan:
            return 'No saved failed scan was found.'
        self.scan_id=scan['id'] # Keep pagination on this scan if a newer run starts.
        self.page=min(self.page,max(0,len(rows)-1))
        self.children[0].disabled=self.page==0
        clean=lambda value,limit=600:diagnostic_text(value,self.client.settings,limit)
        lines=[f'**NCL TRACKER failures — scan {scan["id"]}**',
               f'**State:** {clean(scan["state"],80)} · **Failed challenges:** {len(rows)}']
        try:
            stamp=int(datetime.fromisoformat(scan['started']).timestamp())
            lines.append(f'**Scan started:** <t:{stamp}:f>')
        except (ValueError,TypeError):
            pass
        if scan['channel_id'] and scan['message_id']:
            lines.append(f'[Scan progress]({jump(self.client.settings.guild_id,scan["channel_id"],scan["message_id"])})')
        if not rows:
            lines.append('No failed challenge records remain. A run-level/discovery error may not have an item record; see its progress message. Retried items may already be resolved.')
        else:
            counts=Counter(failure_help(r['error'])[0] for r in rows)
            lines.append('**Reasons:** '+', '.join(f'{name}: {count}' for name,count in counts.items()))
            item=rows[self.page]
            try:
                entry=json.loads(item['entry'])
                if not isinstance(entry,dict):
                    entry={}
            except (ValueError,TypeError):
                entry={}
            kind,help_text=failure_help(item['error'])
            lines.extend([f'**Item {self.page+1}/{len(rows)}: {clean(entry.get("title") or "Unnamed challenge",120)}**',
                          clean(entry.get('event',''),100)+' · '+clean(entry.get('category',''),80),
                          f'**Type:** {kind}',f'**Saved reason:** {clean(item["error"] or "No detailed reason was saved.")}',
                          f'**Next step:** {help_text}'])
            try:
                source=skyline_url(item['url'],'challenge')
            except (ArchiveError,ValueError):
                source=None
            if source:
                lines.append(f'[Open challenge](<{source}>)')
                files=self.client.store.rows("SELECT name,status,error,updated FROM attachments WHERE challenge_key=? AND status NOT IN ('ready','uploaded') AND key NOT IN (SELECT attachment_key FROM evidence) ORDER BY name",
                    (source.split('/module/',1)[1],))
                if files:
                    lines.append('**Current file statuses** (may have changed since this scan):')
                    for f in files[:3]:
                        lines.append(f'{clean(f["name"],60)} — {clean(f["status"],30)}: {clean(f["error"],120)}')
                    if len(files)>3:
                        lines.append(f'Plus {len(files)-3} more files; see the challenge archive for their statuses.')
        lines.append('Refresh to see changes. `/skyline retry-failed` retries the latest failed scan after its cause is fixed.')
        return '\n'.join(lines)[:1950]


class Picker(OwnerView):
    stages=('season','event_url','category','level')
    labels=('Season/year','Competition','Challenge category','Difficulty')

    def __init__(self,client,owner,catalog,warning='',workflow='both'):
        super().__init__(client,owner)
        self.catalog,self.scope,self.stage,self.page=catalog,{},0,0
        self.warning=warning
        self.workflow=workflow
        self.build()

    def choices(self):
        stage=self.stages[self.stage]
        rows=[r for r in self.catalog if matches(r,self.scope)]
        values={r[stage]:(r['event'] if stage=='event_url' else r[stage]) for r in rows}
        return sorted(values.items(),key=lambda x:x[1].casefold())

    def summary(self):
        names={r['event_url']:r['event'] for r in self.catalog}
        selected='\n'.join(f'**{label}:** {names.get(self.scope.get(key),self.scope.get(key,"All"))}'
                           for key,label in zip(self.stages,self.labels))
        count=sum(matches(r,self.scope) for r in self.catalog)
        mode='Discord only' if self.workflow=='discord' else 'Discord first, then GitHub'
        return f'**Choose scan scope**\n**Destination:** {mode}\n{self.warning}\n{selected}\n**Discovered challenges in scope:** {count}\nPreview makes no archive posts, threads, uploads or successful-sync markers.'

    def build(self):
        self.clear_items()
        if self.stage<len(self.stages):
            choices=self.choices()
            start=self.page*24
            options=[discord.SelectOption(label='All',value='all')]+[
                discord.SelectOption(label=label[:100] or 'Unnamed',value=str(i))
                for i,(_,label) in enumerate(choices[start:start+24],start)]
            select=discord.ui.Select(placeholder=self.labels[self.stage],options=options,row=0)
            async def choose(i):
                value=select.values[0]
                if value!='all':
                    self.scope[self.stages[self.stage]]=choices[int(value)][0]
                self.stage+=1
                self.page=0
                self.build()
                await i.response.edit_message(content=self.summary(),view=self)
            select.callback=choose
            self.add_item(select)
            async def previous(i):
                self.page-=1
                self.build()
                await i.response.edit_message(view=self)
            async def following(i):
                self.page+=1
                self.build()
                await i.response.edit_message(view=self)
            self.button('Previous page',previous,disabled=self.page==0)
            self.button('Next page',following,disabled=start+24>=len(choices))
        else:
            async def preview(i):
                await self.client.launch_interaction(i,all_events=True,scope=self.scope,preview=True,workflow=self.workflow)
            async def start(i):
                await self.client.launch_interaction(i,all_events=True,scope=self.scope,preview=False,workflow=self.workflow)
            self.button('Preview',preview,style=discord.ButtonStyle.primary)
            self.button('Start scan',start,style=discord.ButtonStyle.success)
        async def back(i):
            self.stage=max(0,self.stage-1)
            for key in self.stages[self.stage:]:
                self.scope.pop(key,None)
            self.page=0
            self.build()
            await i.response.edit_message(content=self.summary(),view=self)
        self.button('Back',back,row=2,disabled=self.stage==0)
        async def all_scope(i):
            self.scope={}
            self.stage=len(self.stages)
            self.build()
            await i.response.edit_message(content=self.summary(),view=self)
        self.button('Scan everything…',all_scope,row=2)


class SettingModal(discord.ui.Modal):
    def __init__(self,view,key,title):
        super().__init__(title=title)
        self.parent,self.key=view,key
        self.value=discord.ui.TextInput(label=title,default=str(view.client.preferences.effective()[key]),max_length=100,required=False)
        self.add_item(self.value)

    async def on_submit(self,i):
        if not await self.parent.interaction_check(i):
            return
        if self.parent.client.busy():
            await i.response.send_message('Wait for the active scan before changing settings.',ephemeral=True)
            return
        await i.response.defer(ephemeral=True)
        value=str(self.value)
        try:
            if self.key in ('frequency','max_file_mb','cache_mb'):
                value=int(value)
            await self.parent.client.preferences.save({self.key:value},i.guild)
        except (ValueError,ArchiveError) as exc:
            await i.followup.send(str(exc) if isinstance(exc,ArchiveError) else 'Enter a whole number of minutes.',ephemeral=True)
            return
        await i.edit_original_response(content=self.parent.summary('Saved.'),view=self.parent)


class MappingModal(discord.ui.Modal):
    def __init__(self,view):
        super().__init__(title='Map an archive destination')
        self.parent=view
        self.category=discord.ui.TextInput(label='Source category (for category mapping)',required=False,max_length=100)
        self.level=discord.ui.TextInput(label='Legacy difficulty (optional)',required=False,max_length=15)
        self.challenge=discord.ui.TextInput(label='Challenge URL (for challenge channel)',required=False,max_length=200)
        self.destination=discord.ui.TextInput(label='Discord category/channel ID',max_length=22)
        for value in (self.category,self.level,self.challenge,self.destination):
            self.add_item(value)

    async def on_submit(self,i):
        if not await self.parent.interaction_check(i):
            return
        if self.parent.client.busy():
            await i.response.send_message('Wait for the active scan before changing mappings.',ephemeral=True)
            return
        await i.response.defer(ephemeral=True)
        try:
            ident=int(str(self.destination))
            channel=i.guild.get_channel(ident) or await i.guild.fetch_channel(ident)
            if str(self.challenge).strip():
                await self.parent.client.preferences.challenge_mapping(i.guild,str(self.challenge).strip(),channel)
            else:
                await self.parent.client.preferences.mapping(i.guild,str(self.category).strip(),str(self.level).strip().lower(),channel)
        except (ValueError,ArchiveError,discord.HTTPException) as exc:
            message=str(exc) if isinstance(exc,ArchiveError) else 'Destination is unavailable; check its ID and permissions.'
            await i.followup.send(message,ephemeral=True)
            return
        await i.edit_original_response(content=self.parent.summary('Mapping saved. Future scans/reorganize use it; older discussions remain linked.'),view=self.parent)


class SettingsView(OwnerView):
    def __init__(self,client,owner):
        super().__init__(client,owner)
        actions=[('Toggle scheduled scans','enabled'),('Set frequency','frequency'),('Toggle Discord archive','archive_enabled'),
                 ('Toggle default preview','default_preview'),('Toggle login alerts','notify_login'),
                 ('Toggle completion alerts','notify_results'),('Toggle OpenAI assistance','ai_enabled'),
                 ('Maximum file size (MiB)','max_file_mb'),('Private cache budget (MiB)','cache_mb'),
                 ('Set category name prefix','category_prefix'),('Category/channel mapping','mapping')]
        select=discord.ui.Select(placeholder='Change a setting',options=[discord.SelectOption(label=a,value=b) for a,b in actions],row=0)
        async def select_action(i):
            if self.client.busy():
                raise ArchiveError('Wait for the active scan before changing settings.')
            key=select.values[0]
            if key in ('frequency','category_prefix','max_file_mb','cache_mb'):
                labels={'frequency':'Frequency in minutes','category_prefix':'Category prefix',
                        'max_file_mb':'Maximum file size in MiB','cache_mb':'Private cache budget in MiB'}
                await i.response.send_modal(SettingModal(self,key,labels[key]))
            elif key=='mapping':
                await i.response.send_modal(MappingModal(self))
            else:
                await i.response.defer()
                await self.client.preferences.save({key:not self.client.preferences.effective()[key]},i.guild)
                await i.edit_original_response(content=self.summary('Saved.'),view=self)
        select.callback=select_action
        self.add_item(select)
        for row,key,label in ((1,'archive_hub','Archive hub / progress channel'),(2,'notification_channel','Notification destination')):
            control=discord.ui.ChannelSelect(placeholder=label,channel_types=[discord.ChannelType.text],min_values=1,max_values=1,row=row)
            async def choose(i,control=control,key=key):
                if self.client.busy():
                    raise ArchiveError('Wait for the active scan before changing destinations.')
                await i.response.defer()
                await self.client.preferences.save({key:control.values[0].id},i.guild)
                await i.edit_original_response(content=self.summary('Destination saved. Existing archive mappings are retained.'),view=self)
            control.callback=choose
            self.add_item(control)

    def summary(self,notice=''):
        prefs=self.client.preferences.effective()
        labels={'enabled':'scheduled scans','ai_enabled':'AI assistance'}
        rows=[f'**{labels.get(k,k.replace("_"," "))}:** {v}' for k,v in prefs.items()]
        mappings=self.client.store.rows('SELECT kind,scope,discord_id FROM mappings ORDER BY kind,scope')
        mapped='\n'.join(f"{m['scope']} → <#{m['discord_id']}>" for m in mappings[:8]) or 'Created from source categories when archiving is enabled.'
        ai = 'OpenAI: ' + self.client.ai.status() if hasattr(self.client,'ai') else ''
        return ('**NCL TRACKER settings**\n'+notice+'\n'+'\n'.join(rows)+'\n'+ai+'\n**Mappings:**\n'+mapped+
                f'\n{len(mappings)} saved mappings. Private saved settings override environment defaults. Changes apply to the next scan.')[:1950]


class SearchView(OwnerView):
    def __init__(self,client,owner,keywords,filters):
        super().__init__(client,owner)
        self.keywords,self.filters,self.page=keywords,filters,0
        self.more=False
        async def previous(i):
            await i.response.defer()
            self.page=max(0,self.page-1)
            await i.edit_original_response(content=await self.render(i.user),view=self)
        async def following(i):
            await i.response.defer()
            self.page+=1
            await i.edit_original_response(content=await self.render(i.user),view=self)
        self.button('Previous',previous)
        self.button('Next',following)

    async def render(self,member):
        allowed=[]
        for row in self.client.store.rows('SELECT DISTINCT channel_id FROM questions WHERE channel_id IS NOT NULL'):
            try:
                channel=await self.client.archive.channel(row['channel_id'])
            except discord.HTTPException:
                continue
            if channel:
                p=channel.permissions_for(member)
                if p.view_channel and p.read_message_history:
                    allowed.append(channel.id)
        rows=self.client.store.search(self.keywords,self.filters,allowed,include_legacy=member.id in self.client.settings.owners,
                                      offset=self.page*2,limit=3)
        self.more=len(rows)>2
        self.children[0].disabled=self.page==0
        self.children[1].disabled=not self.more
        lines=[f'**Archive search — page {self.page+1}**']
        for q in rows[:2]:
            snippet=q['text'].replace('\n',' ')
            words=self.keywords.casefold().split()
            positions=[snippet.casefold().find(w) for w in words if w in snippet.casefold()]
            at=max(0,min(positions)-45) if positions else 0
            snippet=discord.utils.escape_markdown(snippet[at:at+120])
            links=[]
            if q['message_id']:
                links.append(f"[Question]({jump(self.client.settings.guild_id,q['channel_id'],q['message_id'])})")
            if q['thread_id']:
                try:
                    thread=await self.client.archive.channel(q['thread_id'])
                except discord.HTTPException:
                    thread=None
                if thread and thread.permissions_for(member).view_channel:
                    links.append(f"[Thread](https://discord.com/channels/{self.client.settings.guild_id}/{q['thread_id']})")
            if q['github_path']:
                links.append(f"[GitHub](https://github.com/{self.client.settings.repository}/blob/{quote(self.client.settings.branch,safe='')}/{quote(q['github_path'])})")
            lines.append(f"**{discord.utils.escape_markdown(q['title'])[:120]} · Q{q['number']}**\n{q['season']} / {q['competition']} / {q['category']} / {q['level']}\n{snippet}\n"+' · '.join(links))
        if not rows:
            lines.append('No matching questions visible to you. Use `/skyline reindex` to index older GitHub imports without posting them.')
        return '\n\n'.join(lines)[:1950]


class AnswerModal(discord.ui.Modal):
    def __init__(self,client,question,owner):
        super().__init__(title='Proposed answer — exact text')
        self.client,self.question,self.owner=client,question,owner
        self.answer=discord.ui.TextInput(label='Answer (whitespace is preserved)',style=discord.TextStyle.paragraph,max_length=4000)
        self.add_item(self.answer)

    async def on_submit(self,i):
        if i.user.id!=self.owner or i.user.id not in self.client.settings.owners:
            await i.response.send_message('This answer prompt belongs to its owner.',ephemeral=True)
            return
        await self.client.verify_answer(i,self.question,str(self.answer))


class AnswerPicker(OwnerView):
    def __init__(self,client,owner,question,candidates):
        super().__init__(client,owner)
        self.question,self.candidates,self.page=question,candidates,0
        self.build()

    def build(self):
        self.clear_items()
        if self.candidates:
            values=self.candidates[self.page*25:self.page*25+25]
            select=discord.ui.Select(placeholder='Select the message containing your answer',options=[
                discord.SelectOption(label=f'{m.created_at:%H:%M:%S} {m.content[:75]}',value=str(m.id)) for m in values],row=0)
            async def choose(i):
                selected=next(m for m in values if str(m.id)==select.values[0])
                await self.client.verify_answer(i,self.question,selected.content)
            select.callback=choose
            self.add_item(select)
        async def previous(i):
            self.page-=1; self.build(); await i.response.edit_message(view=self)
        async def following(i):
            self.page+=1; self.build(); await i.response.edit_message(view=self)
        async def provide(i):
            await i.response.send_modal(AnswerModal(self.client,self.question,self.owner))
        self.button('Previous',previous,disabled=self.page==0)
        self.button('Next',following,disabled=(self.page+1)*25>=len(self.candidates))
        self.button('Provide answer',provide,style=discord.ButtonStyle.primary)
