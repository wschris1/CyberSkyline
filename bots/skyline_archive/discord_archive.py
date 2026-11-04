"""Restart-safe Discord archive with stable question identities and recovery markers."""

from datetime import datetime, timedelta
import hashlib

import discord

from .core import ArchiveError, level_and_title, slug
from .storage import digest, now


def pieces(text, size=3500):
    return [text[i:i+size] for i in range(0,len(text),size)] or ['(No additional instructions.)']


def marker(key):
    return 'NCL archive ' + hashlib.sha256(key.encode()).hexdigest()[:32]


def jump(guild, channel, message):
    return f'https://discord.com/channels/{guild}/{channel}/{message}'


class DiscordArchive:
    def __init__(self, client, store, attachments, preferences):
        self.client,self.store,self.attachments,self.preferences = client,store,attachments,preferences
        self.guild_id = client.settings.guild_id

    async def channel(self, ident):
        found = self.client.get_channel(ident)
        if found is None:
            try:
                found = await self.client.fetch_channel(ident)
            except discord.NotFound:
                return None
        if found.guild.id != self.guild_id:
            raise ArchiveError('Stored archive destination belongs to another server.')
        return found

    async def destination(self, c):
        # Retain the original channel when settings change; only missing content uses new mappings.
        previous = self.store.one('SELECT channel_id FROM questions WHERE challenge_key=? AND channel_id IS NOT NULL LIMIT 1',(c.key,))
        if previous:
            channel = await self.channel(previous['channel_id'])
            if channel:
                return self.check_permissions(channel)
        guild = self.client.get_guild(self.guild_id)
        if guild is None:
            raise ArchiveError('Configured Discord server is unavailable.')
        level = level_and_title(c.title)[0]
        category_scope,channel_scope = c.category.casefold(),c.category.casefold()+'/'+level
        mapped = self.store.mapping('channel',channel_scope)
        if mapped:
            channel = await self.channel(mapped)
            if channel:
                return self.check_permissions(channel)
        category = None
        mapped_category = self.store.mapping('category',category_scope)
        if mapped_category:
            category = await self.channel(mapped_category)
        name = (self.preferences.effective()['category_prefix'] + c.category)[:100]
        if category is None:
            candidates = [x for x in guild.categories if x.name == name]
            if len(candidates) > 1:
                raise ArchiveError('Several categories match. Set an explicit category mapping in /skyline settings.')
            if candidates:
                if not self.store.get('creating-category/'+category_scope,False):
                    raise ArchiveError('An unmapped category already has this name. Choose it explicitly in /skyline settings before reusing it.')
                category = candidates[0]
            else:
                overwrites = {guild.default_role:discord.PermissionOverwrite(view_channel=False),
                              guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,
                                                                  read_message_history=True,manage_channels=True,
                                                                  create_public_threads=True,send_messages_in_threads=True,
                                                                  manage_threads=True,attach_files=True,embed_links=True)}
                for owner in self.client.settings.owners:
                    member = guild.get_member(owner) or await guild.fetch_member(owner)
                    overwrites[member] = discord.PermissionOverwrite(view_channel=True,send_messages=True,
                                                                    read_message_history=True,send_messages_in_threads=True)
                self.store.put('creating-category/'+category_scope,True)
                category = await guild.create_category(name,overwrites=overwrites,reason='NCL TRACKER archive')
            self.store.map('category',category_scope,category.id)
            self.store.put('creating-category/'+category_scope,False)
        short = 'passcracking' if c.category.casefold() == 'password cracking' else slug(c.category)
        channel_name = f'{short}-{level}'[:100]
        candidates = [x for x in category.text_channels if x.name == channel_name]
        if len(candidates) > 1:
            raise ArchiveError('Several difficulty channels match. Set an explicit channel mapping.')
        channel = candidates[0] if candidates else await guild.create_text_channel(channel_name,category=category,
            topic=f'NCL TRACKER: {c.category} / {level}. Seasons and competitions are identified per challenge.',
            reason='NCL TRACKER archive')
        self.check_permissions(channel)
        self.store.map('channel',channel_scope,channel.id)
        return channel

    def check_permissions(self, channel):
        needed = ('view_channel','send_messages','read_message_history','embed_links','attach_files',
                  'create_public_threads','send_messages_in_threads','manage_threads')
        if not all(getattr(channel.permissions_for(channel.guild.me),name,False) for name in needed):
            raise ArchiveError('Archive channel permissions are insufficient. Review /skyline settings.')
        return channel

    async def message(self, channel, key, text, file_path=None, filename=None):
        fingerprint = digest([text,str(file_path or ''),filename])
        row = self.store.one('SELECT * FROM posts WHERE key=?',(key,))
        message = None
        if row and row['message_id']:
            old_channel = await self.channel(row['channel_id'])
            if old_channel:
                try:
                    message = await old_channel.fetch_message(row['message_id'])
                    channel = old_channel
                except discord.NotFound:
                    pass
        if row and message is None and row['state'] == 'pending':
            old_channel = await self.channel(row['channel_id'])
            if old_channel:
                channel = old_channel
            # A send may have succeeded just before process loss. Search the complete bounded window.
            seen = 0
            after = datetime.fromisoformat(row['created']) - timedelta(seconds=10)
            async for candidate in channel.history(limit=2001,after=after,oldest_first=True):
                seen += 1
                if candidate.author.id == self.client.user.id and any(e.footer.text == marker(key) for e in candidate.embeds):
                    message = candidate
                    break
            if message is None and seen >= 2001:
                raise ArchiveError('A previous Discord send has uncertain delivery. Reconcile its saved post before retrying; no duplicate was sent.')
        embed = discord.Embed(description=text)
        embed.set_footer(text=marker(key))
        if message is None:
            with self.store.db:
                self.store.db.execute('''INSERT INTO posts VALUES(?,?,NULL,NULL,'pending',?)
                    ON CONFLICT(key) DO UPDATE SET channel_id=excluded.channel_id,message_id=NULL,state='pending',created=excluded.created''',
                    (key,channel.id,now()))
            kwargs = dict(embed=embed,allowed_mentions=discord.AllowedMentions.none())
            if file_path:
                file = discord.File(file_path,filename=filename)
                try:
                    message = await channel.send(file=file,**kwargs)
                finally:
                    file.close()
            else:
                message = await channel.send(**kwargs)
        elif not row or row['fingerprint'] != fingerprint:
            message = await message.edit(embed=embed,allowed_mentions=discord.AllowedMentions.none())
        with self.store.db:
            self.store.db.execute("INSERT INTO posts VALUES(?,?,?,?, 'active',?) ON CONFLICT(key) DO UPDATE SET channel_id=excluded.channel_id,message_id=excluded.message_id,fingerprint=excluded.fingerprint,state='active'",
                                  (key,channel.id,message.id,fingerprint,now()))
        return message

    async def text(self, channel, key, text):
        messages = []
        chunks = pieces(text)
        for index,chunk in enumerate(chunks):
            messages.append(await self.message(channel,f'{key}/part{index}',chunk))
        # Preserve old message/thread IDs, but don't leave stale question text visible.
        old = self.store.rows('SELECT key,channel_id,message_id FROM posts WHERE key LIKE ?', (key+'/part%',))
        for row in old:
            suffix = row['key'][len(key+'/part'):]
            if suffix.isdigit() and int(suffix) >= len(chunks):
                await self.message(channel,row['key'],'This continuation was superseded by the updated question above.')
        return messages

    async def files(self, channel, c, progress=None):
        links = []
        rows = self.store.rows('SELECT * FROM attachments WHERE challenge_key=? ORDER BY name,key',(c.key,))
        for row in rows:
            path = self.attachments.local_path(row)
            if row['status'] not in ('ready','uploaded') or path is None:
                links.append(f"{discord.utils.escape_markdown(row['name'])}: {row['status']} — [open source challenge]({c.url})")
                continue
            # The current guild limit is authoritative, not a hard-coded Discord tier.
            limit = channel.guild.filesize_limit
            if path.stat().st_size > limit:
                if progress:
                    progress.attachment_failed += 1
                self.store.attachment(row['key'],status='oversized-upload',error=f'Exceeds Discord upload limit ({limit} bytes).')
                links.append(f"{discord.utils.escape_markdown(row['name'])}: exceeds this server's {limit}-byte upload limit — [source]({c.url})")
                continue
            try:
                message = await self.message(channel,'file/'+row['key']+'/'+row['sha256'],
                    f"**{discord.utils.escape_markdown(c.title)} — {discord.utils.escape_markdown(row['name'])}**\nSource: <{c.url}>",path,row['name'])
                self.store.attachment(row['key'],status='uploaded',channel_id=message.channel.id,message_id=message.id,error=None)
                links.append(f"[{discord.utils.escape_markdown(row['name'])}]({jump(self.guild_id,message.channel.id,message.id)})")
            except (discord.HTTPException,OSError):
                if progress:
                    progress.attachment_failed += 1
                self.store.attachment(row['key'],status='upload-failed',error='Discord upload failed; retry the scan.')
                links.append(f"{discord.utils.escape_markdown(row['name'])}: upload failed — [source]({c.url})")
        return links

    async def thread(self, parent, q, c):
        thread = await self.channel(q['thread_id']) if q.get('thread_id') else None
        if thread is None:
            # Threads created from a message use that message's ID, including after a crash.
            thread = await self.channel(parent.id)
        if thread is None:
            thread = await parent.create_thread(name=f'{c.title} · Q{q["number"]}'[:100],auto_archive_duration=1440,
                                                reason='NCL TRACKER question discussion')
        if thread.archived:
            if thread.locked:
                raise ArchiveError('A question thread is locked. Unlock it before syncing; its discussion was preserved.')
            await thread.edit(archived=False)
        return thread

    async def publish(self, challenges, progress=None):
        for c in challenges:
            questions = self.store.upsert_challenge(c)
            channel = await self.destination(c)
            if progress:
                progress.update(state='archiving to Discord',competition=c.event,category=c.category,challenge=c.title)
            file_links = await self.files(channel,c,progress)
            context = f'**{c.event}** · {c.category} · {level_and_title(c.title)[0]}\nSource: <{c.url}>\n'
            files = '\n'.join(file_links) or 'No downloadable files listed.'
            headers = await self.text(channel,'challenge/'+c.key,f'## {c.title}\n{context}\n{c.prompt}\n\n**Files**\n{files}')
            header_link = jump(self.guild_id,headers[0].channel.id,headers[0].id)
            for q in questions:
                # A mapping change must not move a previously posted question.
                destination = await self.channel(q['channel_id']) if q.get('channel_id') else channel
                destination = destination or channel
                body = f"## {c.title} — Q{q['number']}\n{context}\n{q['text']}\n\n[Shared instructions]({header_link})\n**Files**\n{files}"
                parents = await self.text(destination,'question/'+q['key'],body)
                thread = await self.thread(parents[0],q,c)
                self.store.link_question(q['key'],parents[0].channel.id,parents[0].id,thread.id)
                # A repaired parent cannot reattach a surviving thread, so always link it explicitly.
                embed = discord.Embed.from_dict(parents[0].embeds[0].to_dict())
                before = embed.to_dict()
                embed.clear_fields()
                embed.add_field(name='Discussion',value=f'[Open question thread](https://discord.com/channels/{self.guild_id}/{thread.id})')
                status = self.store.latest_verification(q['key'])
                if status:
                    embed.add_field(name='Latest verification',value=f"{status['outcome']} · {status['method']}")
                if embed.to_dict() != before:
                    await parents[0].edit(embed=embed,allowed_mentions=discord.AllowedMentions.none())
                intro = f"## {c.title} — Q{q['number']}\n{context}\n{q['text']}\n\n**Instructions**\n{c.prompt}\n\n**Files**\n{files}\n\nDiscuss here. Use `/skyline verify answer:<answer>` to check a proposal without submitting it to Cyber Skyline."
                await self.text(thread,'thread/'+q['key'],intro)
            self.store.synced(c.key)

    async def update_verification(self, question):
        status = self.store.latest_verification(question['key'])
        channel = await self.channel(question['channel_id']) if question['channel_id'] else None
        if not channel or not status:
            return
        key = 'question/'+question['key']+'/part0'
        row = self.store.one('SELECT * FROM posts WHERE key=?',(key,))
        if not row or not row['message_id']:
            return
        try:
            message = await channel.fetch_message(row['message_id'])
        except discord.NotFound:
            return
        # Keep the complete question in its existing continuation messages.
        embed = message.embeds[0]
        index = next((i for i,field in enumerate(embed.fields) if field.name == 'Latest verification'),None)
        value = f"{status['outcome']} · {status['method']}"
        if index is None:
            embed.add_field(name='Latest verification',value=value)
        else:
            embed.set_field_at(index,name='Latest verification',value=value)
        await message.edit(embed=embed,allowed_mentions=discord.AllowedMentions.none())
