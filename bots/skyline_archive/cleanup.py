"""Explicit, owner-confirmed Discord cleanup backed by a fresh GitHub proof."""

import asyncio
from dataclasses import dataclass
import time

import discord

from .core import ArchiveError
from .discord_archive import is_marker
from .github import GitHub
from .scanner import matches
from .storage import digest, fingerprint
from .workflows import catalog_entry


WARNING = ('Deleting channels permanently removes their messages, question threads, answers, discussions and '
           'Discord uploads. GitHub contains sanitized question prompts, not those conversations or file backups. '
           'Private source snapshots, cached files and verification records stay on the host. GitHub is never changed.')


@dataclass
class CleanupPlan:
    head: str
    repository: str
    branch: str
    scope: dict
    origin: int
    items: list
    skipped: list
    created: float

    @property
    def channels(self):
        return [i for i in self.items if i['kind']=='channel']

    @property
    def categories(self):
        return [i for i in self.items if i['kind']=='category']

    @property
    def signature(self):
        return digest([self.head,self.repository,self.branch,self.scope,self.origin,self.items])

    @property
    def phrase(self):
        return f'DELETE {len(self.channels)} CHANNELS {len(self.categories)} CATEGORIES'


class Cleanup:
    def __init__(self, client):
        self.client, self.store = client, client.store
        self.github = GitHub(client.settings,client.http_session)

    def protected(self, origin):
        prefs = self.client.preferences.effective()
        return {origin,prefs['archive_hub'],prefs['notification_channel'],self.store.get('last_command_channel',0)} | {int(k) for k,w in self.store.get('leaderboards',{}).items() if w.get('state')=='active' or w.get('pending')}

    async def inventory(self):
        guild = self.client.get_guild(self.client.settings.guild_id)
        if not guild:
            raise ArchiveError('The configured Discord server is unavailable. Cleanup is blocked.')
        # A REST inventory, not stale gateway category/channel caches.
        channels = {c.id:c for c in await guild.fetch_channels()}
        return guild, channels

    async def recover(self):
        """Reconcile uncertain deletes; never issue a new delete after a restart."""
        pending = self.store.rows("SELECT * FROM discord_cleanup WHERE state IN ('pending','failed')")
        if not pending:
            return
        _, channels = await self.inventory()
        for row in pending:
            if row['channel_id'] not in channels:
                self.store.finish_discord_cleanup(row['channel_id'])
            elif row['state']=='pending':
                self.store.fail_discord_cleanup(row['channel_id'],'Interrupted; run a new cleanup preview before retrying.')

    def keys_in(self, ident):
        rows = self.store.rows('''SELECT DISTINCT challenge_key FROM questions WHERE channel_id=?
            UNION SELECT DISTINCT q.challenge_key FROM question_locations l JOIN questions q ON q.key=l.question_key WHERE l.channel_id=?
            UNION SELECT scope FROM mappings WHERE kind='challenge-channel' AND discord_id=?''',(ident,ident,ident))
        return sorted(r['challenge_key'] for r in rows)

    async def managed(self, channel, keys):
        topic = getattr(channel,'topic','') or ''
        if not (any(topic.startswith(prefix+key+' |') for key in keys for prefix in ('WS challenge ','NCL challenge ')) or topic.startswith(('WS: ','NCL TRACKER: '))):
            return False
        # Do not interpret names or a manually supplied mapping as proof of ownership.
        posts = self.store.rows("SELECT key,message_id FROM posts WHERE channel_id=? AND state='active' AND message_id IS NOT NULL",(channel.id,))
        for row in posts:
            try:
                message = await channel.fetch_message(row['message_id'])
            except discord.NotFound:
                continue
            if message.author.id==channel.guild.me.id and any(is_marker(e.footer.text,row['key']) for e in message.embeds):
                return True
        return False

    async def plan(self, scope, origin):
        proof = await self.github.archive_proof()
        guild, channels = await self.inventory()
        protected = self.protected(origin)
        protected.update(getattr(guild,k,None) for k in ('system_channel_id','rules_channel_id','public_updates_channel_id','safety_alerts_channel_id'))
        mapped = self.store.rows("SELECT * FROM mappings WHERE kind IN ('channel','challenge-channel','category')")
        candidates = {r['discord_id'] for r in mapped if r['kind']!='category'}
        candidates.update(r['channel_id'] for r in self.store.rows('SELECT DISTINCT channel_id FROM question_locations'))
        candidates.update(r['channel_id'] for r in self.store.rows('SELECT DISTINCT channel_id FROM questions WHERE channel_id IS NOT NULL'))
        items, skipped = [], []
        for ident in sorted(candidates):
            channel = channels.get(ident)
            if channel is None:
                continue
            keys = self.keys_in(ident)
            snapshots = [self.store.snapshot(key) for key in keys]
            why = None
            if ident in protected:
                why = 'Protected progress, notification, command or system channel.'
            elif channel.type!=discord.ChannelType.text or not keys or any(c is None for c in snapshots):
                why = 'No complete, managed challenge identity.'
            elif not all(matches(catalog_entry(c),scope) for c in snapshots):
                why = 'Contains challenges outside the selected scope; shared channels are kept whole.'
            elif not all(getattr(channel.permissions_for(guild.me),p,False) for p in ('view_channel','read_message_history','manage_channels')):
                why = 'Missing View Channel, Read Message History or Manage Channels permission.'
            else:
                for c in snapshots:
                    saved = self.store.rows('SELECT text FROM questions WHERE challenge_key=? ORDER BY number',(c.key,))
                    if tuple(q['text'] for q in saved)!=c.questions:
                        why = 'Saved question rows and source snapshot disagree; reconcile before cleanup.'
                        break
                    why = proof.check(c)
                    if why:
                        break
                if not why and not await self.managed(channel,keys):
                    why = 'Archive ownership could not be confirmed from topic and bot post markers.'
            if why:
                skipped.append(dict(id=ident,name=channel.name,reason=why))
                continue
            locations = self.store.rows('SELECT * FROM question_locations WHERE channel_id=? ORDER BY thread_id',(ident,))
            current = self.store.rows('SELECT key,challenge_key,number,channel_id,message_id,thread_id FROM questions WHERE channel_id=? ORDER BY key',(ident,))
            retire = {q['challenge_key'] for q in current}
            retire.update(r['scope'] for r in mapped if r['kind']=='challenge-channel' and r['discord_id']==ident)
            threads = sorted({r['thread_id'] for r in [*locations,*current] if r['thread_id']})
            items.append(dict(id=ident,kind='channel',name=channel.name,category=channel.category_id,
                topic=channel.topic,keys=keys,retire=sorted(retire),threads=threads,
                locations=locations,current=current,fingerprints={c.key:fingerprint(c) for c in snapshots},
                files={key:proof.manifest[key]['files'] for key in keys}))
        eligible = {i['id'] for i in items}
        category_maps = {r['discord_id'] for r in mapped if r['kind']=='category'}
        for ident in sorted(category_maps):
            channel = channels.get(ident)
            if not channel or channel.type!=discord.ChannelType.category or ident in protected:
                continue
            children = {c.id for c in channels.values() if getattr(c,'category_id',None)==ident}
            # Empty mapped categories from a partial cleanup can be retried after proof.
            scopes = [r['scope'] for r in mapped if r['kind']=='category' and r['discord_id']==ident]
            keys = [r['key'] for r in self.store.rows('SELECT key,category FROM challenges') if r['category'].casefold() in scopes]
            evidence = [self.store.snapshot(key) for key in keys]
            known = bool(evidence) and all(matches(catalog_entry(c),scope) and not proof.check(c) for c in evidence)
            if (children and children<=eligible) or (not children and known):
                if channel.permissions_for(guild.me).manage_channels:
                    items.append(dict(id=ident,kind='category',name=channel.name,children=sorted(children)))
                else:
                    skipped.append(dict(id=ident,name=channel.name,reason='Category: missing Manage Channels permission.'))
            else:
                skipped.append(dict(id=ident,name=channel.name,reason='Category contains retained channels or lacks complete GitHub proof.'))
        return CleanupPlan(proof.head,self.client.settings.repository,self.client.settings.branch,dict(scope),origin,items,skipped,time.monotonic())

    async def execute(self, approved, owner, notify=None):
        if owner not in self.client.settings.owners or time.monotonic()-approved.created>600:
            raise ArchiveError('Cleanup approval is expired or unauthorized. Run a fresh preview.')
        await self.recover()
        fresh = await self.plan(approved.scope,approved.origin)
        if fresh.signature!=approved.signature:
            raise ArchiveError('GitHub or the Discord archive changed after preview. Nothing was deleted; run a fresh preview.')
        deleted, failures = [], []
        for item in fresh.items:
            # Verify branch stability immediately before each irreversible request.
            if await self.github.head()!=fresh.head:
                failures.append('GitHub changed during cleanup; remaining channels and categories were kept.')
                break
            _, inventory = await self.inventory()
            channel = inventory.get(item['id'])
            if channel is None:
                continue
            if (channel.name!=item['name'] or item['id'] in self.protected(approved.origin) or
                    not channel.permissions_for(channel.guild.me).manage_channels):
                failures.append(f"{item['name']}: destination or permissions changed; kept.")
                continue
            if item['kind']=='category':
                if any(getattr(c,'category_id',None)==channel.id for c in inventory.values()):
                    failures.append(f"{item['name']}: category is not empty; kept.")
                    continue
            elif channel.category_id!=item['category'] or channel.topic!=item['topic'] or self.keys_in(channel.id)!=item['keys']:
                failures.append(f"{item['name']}: archive identity changed; kept.")
                continue
            self.store.begin_discord_cleanup(item,fresh.head,owner)
            try:
                await channel.delete(reason=f'WS owner {owner}: prompts verified at {fresh.head[:12]}')
            except discord.NotFound:
                pass
            except (discord.HTTPException,asyncio.TimeoutError,OSError) as exc:
                error = f'Discord deletion failed ({type(exc).__name__}); rerun preview to reconcile/retry.'
                self.store.fail_discord_cleanup(item['id'],error)
                failures.append(f"{item['name']}: {error}")
                continue
            self.store.finish_discord_cleanup(item['id'])
            deleted.append(item)
            if notify:
                await notify(len(deleted),len(fresh.items))
        return deleted, failures

    def allow_recreation(self, scope):
        keys = [r['challenge_key'] for r in self.store.rows('SELECT challenge_key FROM discord_retirements')
                if matches(catalog_entry(self.store.snapshot(r['challenge_key'])),scope)]
        self.store.allow_discord_recreation(keys)
        return len(keys)


async def locked(client, phase, operation):
    """Share the scan/schedule/settings mutex, including while awaiting network I/O."""
    if client.busy():
        raise ArchiveError('A scan or archive operation is running. Wait or pause it before cleanup.')
    client.scan_phase = phase
    client.scan_task = asyncio.create_task(operation())
    try:
        return await client.scan_task
    finally:
        client.scan_phase = 'idle'
