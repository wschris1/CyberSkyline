"""Independent archive destinations and a single durable Discord publishing queue."""

import asyncio

import discord

from .core import ArchiveError, event_location, level_and_title
from .discord_archive import marker
from .scanner import matches
from .storage import fingerprint, now


def github_target(settings):
    return f'github:{settings.repository}:{getattr(settings,"branch","main")}'


def catalog_entry(c):
    season, competition = event_location(c.event)
    return dict(url=c.url,event=c.event,event_url='https://cyberskyline.com/world/'+c.ids[0],
                season=season,competition=competition,category=c.category,title=c.title,
                level=level_and_title(c.title)[0])


class DiscordPipeline:
    """One publisher avoids category/channel races while source collection continues.

    Only URLs live in the queue; full snapshots are already committed to SQLite.
    Cancelling a worker preserves pending sends and their recovery markers.
    """
    def __init__(self, client, scan_id, enabled, progress):
        self.client, self.scan_id, self.enabled, self.progress = client, scan_id, enabled, progress
        self.queue = asyncio.Queue()
        self.offered = set()
        self.errors = []
        self.completed = 0
        self.task = asyncio.create_task(self.run())

    def offer(self, url):
        if url not in self.offered:
            self.offered.add(url)
            self.queue.put_nowait(url)

    async def run(self):
        while True:
            url = await self.queue.get()
            if url is None:
                return
            row = self.client.store.one('SELECT payload FROM scan_items WHERE scan_id=? AND url=?',
                                        (self.scan_id,url))
            if not row or not row['payload']:
                continue
            c = self.client.store.decode_challenge(row['payload'])
            try:
                if self.client.scan_options.get('scheduled') and self.client.store.discord_retired(c.key):
                    self.client.jobs.state(self.scan_id,url,'published')
                    continue
                if self.enabled:
                    await self.client.archive.publish([c],self.progress)
                    self.progress.discord_completed += 1
                failed_files = self.client.store.rows("SELECT key FROM attachments WHERE challenge_key=? "
                    "AND status IN ('failed','unavailable','cache-full','oversized','upload-failed','missing-cache') "
                    "AND key NOT IN (SELECT attachment_key FROM evidence)",(c.key,))
                if failed_files:
                    error = 'Files need retry; collected questions and existing posts were preserved.'
                    self.client.jobs.state(self.scan_id,url,'failed',error)
                    # Resume must revisit the authenticated source for failed downloads.
                    with self.client.store.db:
                        self.client.store.db.execute('UPDATE scan_items SET payload=NULL WHERE scan_id=? AND url=?',
                                                     (self.scan_id,url))
                    self.errors.append(f'{c.title}: {error}')
                    self.progress.publication_failed += 1
                else:
                    self.client.jobs.state(self.scan_id,url,'published')
                self.completed += 1
                if self.enabled:
                    self.client.store.put('last_success',now())
            except (ArchiveError,discord.HTTPException,OSError,asyncio.TimeoutError) as exc:
                error = str(exc) if isinstance(exc,ArchiveError) else (
                    f'Discord publication failed ({type(exc).__name__}); saved posts will be reused.')
                self.client.jobs.state(self.scan_id,url,'failed',error)
                self.errors.append(f'{c.title}: {error}')
                self.progress.publication_failed += 1
            finally:
                self.progress.discord_challenge = ''

    async def finish(self):
        self.queue.put_nowait(None)
        await self.task

    async def close(self):
        if not self.task.done():
            self.task.cancel()
        await asyncio.gather(self.task,return_exceptions=True)


async def mapped_archives(client, scope, channel_id=0):
    """Select canonical prompts attached to known Discord question posts.

    Never enumerate arbitrary chat, read answer threads, or turn message bodies
    into public source text. The source snapshot remains authoritative even if
    someone appends an answer to an embed. Validate each mapped parent exists.
    """
    candidates = []
    for row in client.store.rows('SELECT key FROM challenges ORDER BY season,competition,category,title,key'):
        c = client.store.snapshot(row['key'])
        if not matches(catalog_entry(c),scope):
            continue
        questions = client.store.rows('SELECT * FROM questions WHERE challenge_key=? ORDER BY number',(c.key,))
        if not questions or not any(q['channel_id'] for q in questions):
            continue
        if channel_id and not any(q['channel_id']==channel_id for q in questions):
            continue
        candidates.append((c,questions))
    return candidates


async def validate_parents(client, c, questions):
    saved=client.store.one('SELECT synced_fingerprint FROM challenges WHERE key=?',(c.key,))
    delivery=client.store.one("SELECT fingerprint FROM deliveries WHERE challenge_key=? AND target='discord'",(c.key,))
    if (not saved or saved['synced_fingerprint']!=fingerprint(c) or
            (delivery and delivery['fingerprint']!=fingerprint(c))):
        raise ArchiveError('This source snapshot has not finished archiving to Discord; run scan-discord or resume first.')
    if len(questions) != len(c.questions):
        raise ArchiveError('Saved question count does not match the Discord archive; repair with scan-discord first.')
    channels = {}
    for q in questions:
        if not q['channel_id'] or not q['message_id']:
            raise ArchiveError('A question has no Discord parent post; run scan-discord to finish its archive first.')
        if q['channel_id'] not in channels:
            channel = await client.archive.channel(q['channel_id'])
            if channel is None:
                raise ArchiveError('A mapped Discord channel is missing; repair with scan-discord first.')
            perms = channel.permissions_for(channel.guild.me)
            if not perms.view_channel or not perms.read_message_history:
                raise ArchiveError('Cannot read a mapped Discord channel; restore View Channel and Read Message History.')
            channels[q['channel_id']] = channel
        try:
            message = await channels[q['channel_id']].fetch_message(q['message_id'])
        except discord.NotFound:
            raise ArchiveError('A mapped question post is missing; repair with scan-discord first.') from None
        post = client.store.one('SELECT key FROM posts WHERE channel_id=? AND message_id=? AND state=?',
                                (q['channel_id'],q['message_id'],'active'))
        if (not post or message.author.id != channels[q['channel_id']].guild.me.id or
                not any(e.footer.text == marker(post['key']) for e in message.embeds)):
            raise ArchiveError('A question post could not be identified as a managed bot archive; nothing from its conversation was exported.')
