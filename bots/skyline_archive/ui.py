"""Owner-bound Discord components, staged menus and permission-aware result pages."""

import json
from urllib.parse import quote

import discord

from .core import ArchiveError
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


class Picker(OwnerView):
    stages=('season','event_url','category','level')
    labels=('Season/year','Competition','Challenge category','Difficulty')

    def __init__(self,client,owner,catalog,warning=''):
        super().__init__(client,owner)
        self.catalog,self.scope,self.stage,self.page=catalog,{},0,0
        self.warning=warning
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
        return f'**Choose scan scope**\n{self.warning}\n{selected}\n**Discovered challenges in scope:** {count}\nPreview makes no archive posts, threads, uploads or successful-sync markers.'

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
                await self.client.launch_interaction(i,all_events=True,scope=self.scope,preview=True)
            async def start(i):
                await self.client.launch_interaction(i,all_events=True,scope=self.scope,preview=False)
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
            if self.key=='frequency':
                value=int(value)
            await self.parent.client.preferences.save({self.key:value},i.guild)
        except (ValueError,ArchiveError) as exc:
            await i.followup.send(str(exc) if isinstance(exc,ArchiveError) else 'Enter a whole number of minutes.',ephemeral=True)
            return
        await i.edit_original_response(content=self.parent.summary('Saved.'),view=self.parent)


class MappingModal(discord.ui.Modal):
    def __init__(self,view):
        super().__init__(title='Map a source category or difficulty')
        self.parent=view
        self.category=discord.ui.TextInput(label='Exact source category name',max_length=100)
        self.level=discord.ui.TextInput(label='Difficulty (blank to map category)',required=False,max_length=15)
        self.destination=discord.ui.TextInput(label='Discord category/channel ID',max_length=22)
        for value in (self.category,self.level,self.destination):
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
            await self.parent.client.preferences.mapping(i.guild,str(self.category).strip(),str(self.level).strip().lower(),channel)
        except (ValueError,ArchiveError,discord.HTTPException) as exc:
            message=str(exc) if isinstance(exc,ArchiveError) else 'Destination is unavailable; check its ID and permissions.'
            await i.followup.send(message,ephemeral=True)
            return
        await i.edit_original_response(content=self.parent.summary('Mapping saved; existing posts stay in their original channels.'),view=self.parent)


class SettingsView(OwnerView):
    def __init__(self,client,owner):
        super().__init__(client,owner)
        actions=[('Toggle scheduled scans','enabled'),('Set frequency','frequency'),('Toggle Discord archive','archive_enabled'),
                 ('Toggle default preview','default_preview'),('Toggle login alerts','notify_login'),
                 ('Toggle completion alerts','notify_results'),('Toggle OpenAI assistance','ai_enabled'),
                 ('Set category name prefix','category_prefix'),('Category/channel mapping','mapping')]
        select=discord.ui.Select(placeholder='Change a setting',options=[discord.SelectOption(label=a,value=b) for a,b in actions],row=0)
        async def select_action(i):
            if self.client.busy():
                raise ArchiveError('Wait for the active scan before changing settings.')
            key=select.values[0]
            if key in ('frequency','category_prefix'):
                await i.response.send_modal(SettingModal(self,key,'Frequency in minutes' if key=='frequency' else 'Category prefix'))
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
