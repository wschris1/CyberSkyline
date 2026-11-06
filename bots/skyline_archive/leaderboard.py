"""Read-only standings and restart-safe, owner-managed Discord update schedules."""

import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid

import discord

from .core import ArchiveError, SessionExpired
from .scanner import Scanner

LOG = logging.getLogger(__name__)
EXTRACTOR = Path(__file__).with_name('leaderboard_dom.js').read_text(encoding='utf-8')


def leaderboard_url(value):
    try:
        p = urlsplit(value.strip())
        valid = (p.scheme == 'https' and p.hostname == 'cyberskyline.com' and
                 not p.username and not p.password and p.port in (None, 443) and
                 not p.query and not p.fragment and
                 re.fullmatch(r'/world/[a-fA-F0-9]{24}(?:/leaderboard)?/?', p.path))
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise ArchiveError('Use a Cyber Skyline event leaderboard link: https://cyberskyline.com/world/<event ID>/leaderboard. '
                           'Open the specific competition leaderboard, not a season results page.')
    return 'https://cyberskyline.com' + p.path.rstrip('/').removesuffix('/leaderboard') + '/leaderboard'


def interval_seconds(value):
    match = re.fullmatch(r'\s*([0-9]{1,5})\s*(m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)?\s*', value or '', re.I)
    if not match:
        raise ArchiveError('Use a whole-minute interval such as 10, 10m, 30 minutes, 1h or 1d.')
    unit = (match[2] or 'm').lower()[0]
    seconds = int(match[1]) * {'m': 60, 'h': 3600, 'd': 86400}[unit]
    if not 60 <= seconds <= 604800:
        raise ArchiveError('Leaderboard updates must be between 1 minute and 7 days apart.')
    return seconds


def integer(value):
    value = str(value).strip().replace(',', '')
    return int(value) if re.fullmatch(r'\d{1,12}', value) else None


def rows_from(snapshot):
    rows = []
    for table in snapshot.get('tables', []):
        headers = [h.strip().lower() for h in table.get('headers', [])]
        if not all(h in headers for h in ('rank', 'handle', 'points')):
            continue
        for raw in table.get('rows', []):
            cells = raw.get('cells', [])
            if len(cells) != len(headers):
                continue
            values = dict(zip(headers, cells))
            rank, points = integer(values['rank']), integer(values['points'])
            if rank is None or rank < 1 or points is None or not values['handle'].strip():
                continue
            rows.append(dict(id=raw.get('id', ''), name=values['handle'][:200], rank=rank, points=points,
                             accuracy=values.get('accuracy', '')[:30], completion=values.get('completion', '')[:30],
                             own=bool(raw.get('own'))))
    # Distinct IDs are not merged just because two competitors have the same handle.
    return list({(r['id'], r['name'], r['rank']): r for r in rows}.values())


def snapshot_from(neighbors, top, previous_identity='', expected_name=''):
    statuses = ' '.join(neighbors.get('statuses', []))
    unranked = bool(re.search(r'unranked|theoretical', statuses, re.I))
    m = re.search(r'Rank\s*:\s*([\d,]+)\s*/\s*([\d,]+)', statuses, re.I)
    rank, total = (integer(m[1]), integer(m[2])) if m else (None, None)
    if not unranked and (not rank or not total or rank > total):
        raise ArchiveError('Your leaderboard rank is not available yet. Waiting for a consistent rank and total.')
    nearby = rows_from(neighbors)
    marked = [r for r in nearby if r['own']]
    # Never substitute the occupant of a theoretical rank for an unranked account.
    own = marked[0] if len(marked) == 1 else None
    if own is None and not unranked and rank:
        candidates = [r for r in nearby if r['rank'] == rank]
        if len(candidates) == 1:
            own = candidates[0]
    if own and rank and own['rank'] != rank:
        raise ArchiveError('The leaderboard changed while loading. Waiting for a consistent rank and row.')
    if own and expected_name and own['name'].casefold() != expected_name.strip().casefold():
        raise ArchiveError('The signed-in leaderboard identity does not match team:. Check the selected account/event.')
    identity = (own['id'] or 'name:' + own['name']) if own else ''
    if previous_identity and identity and identity != previous_identity:
        raise ArchiveError('The signed-in leaderboard identity changed. Run /ws leaderboard again to confirm the new account/team.')
    if not own and not unranked:
        # Do not guess from the first row or use an old score as a fresh result.
        raise ArchiveError('Your ranked row is not available yet. The event may be unopened, unranked, hidden or loading.')
    top_rows = [r for r in rows_from(top) if r['rank'] <= 10]
    if not top_rows or not any(r['rank'] == 1 for r in top_rows):
        raise ArchiveError('The top leaderboard rows are not available yet; no fresh standings were posted.')
    nearby = [r for r in nearby if rank and abs(r['rank'] - rank) <= 2]
    return dict(title=neighbors.get('title') or 'Competition leaderboard', own=own, rank=rank,
                total=total, unranked=unranked, identity=identity, top=top_rows[:10], nearby=nearby,
                filters=neighbors.get('filters', []), checked=int(time.time()))


class LeaderboardReader:
    def __init__(self, settings):
        self.settings = settings

    async def read(self, url, identity='', team=''):
        from playwright.async_api import Error as PlaywrightError
        url = leaderboard_url(url)
        scanner = Scanner(self.settings)
        try:
            async with scanner.opened() as context:
                # This feature is read-only. Block unsafe navigations and all writes from this page.
                async def guard(route):
                    request = route.request
                    p = urlsplit(request.url)
                    permitted = (p.scheme == 'https' and (p.hostname == 'cyberskyline.com' or
                                 p.hostname == 'builds.cyberskyline.com') and request.method in ('GET', 'HEAD'))
                    if permitted:
                        await route.continue_()
                    else:
                        await route.abort()
                await context.route('**/*', guard)
                page = scanner.page
                response = await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                if response and response.status == 401:
                    raise SessionExpired('Cyber Skyline login expired; refresh it and run /ws session recheck.')
                if response and response.status >= 400:
                    raise ArchiveError(f'Leaderboard returned HTTP {response.status}. Check access or try later.')
                initial = await self.wait(page, own=True)
                neighbors = page.get_by_role('tab', name='Neighbors', exact=True)
                if await neighbors.count():
                    await neighbors.click()
                    initial = await self.wait(page, own=True)
                tabs = page.get_by_role('tab', name=re.compile(r'^Top (Players|Teams)$'))
                if await tabs.count() != 1:
                    raise ArchiveError('The leaderboard tabs are unavailable or ambiguous.')
                await tabs.click()
                top = await self.wait(page, own=False)
                return snapshot_from(initial, top, identity, team)
        except PlaywrightError:
            raise ArchiveError('Leaderboard navigation timed out or the page could not be read. No stale standings were posted.') from None

    async def wait(self, page, own):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            p = urlsplit(page.url)
            if any(part in p.path.lower() for part in ('login', 'sign-in', 'signin')):
                raise SessionExpired('Cyber Skyline login expired; refresh it and run /ws session recheck.')
            if p.hostname != 'cyberskyline.com':
                raise ArchiveError('Leaderboard redirected to an unexpected website.')
            snapshot = await page.evaluate(EXTRACTOR)
            if snapshot.get('login'):
                raise SessionExpired('Cyber Skyline needs a refreshed login; run /ws session recheck afterward.')
            status = ' '.join(snapshot.get('statuses', []))
            rows = rows_from(snapshot)
            if own and re.search(r'unranked|theoretical', status, re.I):
                return snapshot
            rank = re.search(r'Rank\s*:\s*([\d,]+)', status, re.I)
            if own and rank and any(r['rank'] == integer(rank[1]) for r in rows):
                return snapshot
            if own:
                neighbors = page.get_by_role('tab', name='Neighbors', exact=True)
                if await neighbors.count() == 1 and await neighbors.get_attribute('aria-selected') != 'true':
                    await neighbors.click()
            if not own and any(r['rank'] == 1 for r in rows):
                return snapshot
            await asyncio.sleep(0.5)
        raise ArchiveError('Leaderboard standings are not available yet. The event may be unopened or its rankings hidden.')


def safe(value, limit=120):
    return discord.utils.escape_markdown(discord.utils.escape_mentions(str(value).replace('\n', ' ')))[:limit]


def report(snapshot, watch, previous=None):
    own = snapshot['own']
    rank, total = snapshot['rank'], snapshot['total']
    if snapshot['unranked']:
        standing = f'Unranked — theoretical position #{rank:,}' if rank else 'Unranked — no published position'
    else:
        standing = f'**#{rank:,}' + (f' / {total:,}' if total else '') + '**'
    lines = [standing]
    if own:
        lines += [f"**{safe(own['name'])}** · **{own['points']:,} points**",
                  f"Accuracy: {safe(own['accuracy']) or 'unavailable'} · Completion: {safe(own['completion']) or 'unavailable'}"]
    if previous and previous.get('identity') and previous['identity'] == snapshot['identity']:
        if not snapshot['unranked'] and not previous.get('unranked') and previous.get('rank') and rank:
            delta = previous['rank'] - rank
            lines.append(f"Since last report: {'up' if delta > 0 else 'down'} {abs(delta):,} places" if delta else 'Since last report: rank unchanged')
        if own and previous.get('own'):
            lines.append(f"Points change: {own['points'] - previous['own']['points']:+,}")
    embed = discord.Embed(title=('WS · ' + snapshot['title'])[:256], url=watch['url'],
                          description='\n'.join(lines), color=0x30C9C3,
                          timestamp=datetime.fromtimestamp(snapshot['checked'], timezone.utc))
    line = lambda r: f"**#{r['rank']}** {safe(r['name'], 65)} — {r['points']:,} pts"
    embed.add_field(name='Top 10', value='\n'.join(line(r) for r in snapshot['top'])[:1024], inline=False)
    if snapshot['nearby']:
        embed.add_field(name='Around your position', value='\n'.join(line(r) for r in snapshot['nearby'])[:1024], inline=False)
    embed.add_field(name='Updates', value=f"Every {watch['interval']//60:,} minutes · checked <t:{snapshot['checked']}:R>\n"
                    'Rank is reported by Cyber Skyline; equal points can have different ranks.', inline=False)
    if snapshot.get('filters'):
        embed.add_field(name='Leaderboard scope', value=' · '.join(safe(v) for v in snapshot['filters'])[:1024], inline=False)
    return embed


class Leaderboards:
    """One persistent watch per channel; one shared browser/scan job at a time."""
    def __init__(self, client, reader=None, clock=time.time):
        self.client, self.store = client, client.store
        self.reader = reader or LeaderboardReader(client.settings)
        self.clock = clock
        self.watches = self.store.get('leaderboards', {})

    def save(self):
        self.store.put('leaderboards', self.watches)

    def configure(self, channel, owner, url, interval, team=''):
        if len(team) > 200:
            raise ArchiveError('The optional team name must be at most 200 characters.')
        key = str(channel.id)
        if key not in self.watches and len(self.watches) >= 20:
            raise ArchiveError('At most 20 leaderboard destinations are supported.')
        old = self.watches.get(key, {})
        if old.get('pending'):
            raise ArchiveError('A previous report has uncertain delivery. Use action:now to reconcile it before changing this watch.')
        self.watches[key] = dict(url=leaderboard_url(url), interval=interval_seconds(interval),
            channel=channel.id, guild=channel.guild.id, owner=owner, team=team.strip(), state='active',
            due=self.clock(), previous=None, identity='', errors=0, status='Waiting for first report', pending=None)
        self.save()
        return self.watches[key]

    async def destination(self, watch):
        if watch['guild'] != self.client.settings.guild_id or watch['owner'] not in self.client.settings.owners:
            raise ArchiveError('Leaderboard watch owner/server is no longer authorized.')
        channel = await self.client.archive.channel(watch['channel'])
        if channel is None or not isinstance(channel, discord.TextChannel) or channel.guild.id != watch['guild']:
            raise ArchiveError('The leaderboard destination is not an available text channel.')
        permissions = channel.permissions_for(channel.guild.me)
        if not all(getattr(permissions, p, False) for p in ('view_channel', 'send_messages', 'embed_links', 'read_message_history')):
            raise ArchiveError('Leaderboard channel needs View Channel, Send Messages, Embed Links and Read Message History.')
        return channel

    async def tick(self):
        if self.client.busy():
            return
        due = [w for w in self.watches.values() if w['state'] == 'active' and w['due'] <= self.clock()]
        if not due:
            return
        if self.store.get('auth_invalid', False):
            changed = False
            for watch in due:
                status = 'Waiting for login refresh and /ws session recheck'
                if not watch.get('pending') and watch['status'] != status:
                    watch['status'] = status
                    changed = True
            if changed:
                self.save()
            # Saved reports can be reconciled without contacting Cyber Skyline.
            due = [w for w in due if w.get('pending')]
            if not due:
                return
        watch = min(due, key=lambda w: w['due'])
        self.client.scan_phase = 'leaderboard'
        task = self.client.scan_task = asyncio.create_task(self.run(watch))
        try:
            await task
        except asyncio.CancelledError:
            if not task.cancelled():
                task.cancel()
            raise
        finally:
            if self.client.scan_task is task:
                self.client.scan_phase = 'idle'

    async def deliver(self, channel, watch):
        pending = watch['pending']
        marker = pending['marker']
        after = datetime.fromtimestamp(pending['created'], timezone.utc) - timedelta(seconds=10)
        count = 0
        async for message in channel.history(limit=1001, after=after, oldest_first=True):
            count += 1
            if message.author.id == self.client.user.id and any(e.footer.text == marker for e in message.embeds):
                return message.id
        if count >= 1001:
            raise ArchiveError('Report delivery is uncertain because channel history is too busy. No duplicate was sent; check the saved report.')
        embed = discord.Embed.from_dict(pending['embed'])
        message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        return message.id

    async def run(self, watch):
        try:
            channel = await self.destination(watch)
            if not watch.get('pending'):
                snapshot = await asyncio.wait_for(self.reader.read(watch['url'], watch['identity'], watch['team']), 120)
                embed = report(snapshot, watch, watch.get('previous'))
                marker = 'WS leaderboard ' + uuid.uuid4().hex
                embed.set_footer(text=marker)
                watch['pending'] = dict(created=self.clock(), marker=marker, snapshot=snapshot, embed=embed.to_dict())
                self.save()  # Before send: recover a successful send followed by process loss.
            message_id = await self.deliver(channel, watch)
            watch.update(previous=watch['pending']['snapshot'], identity=watch['pending']['snapshot']['identity'],
                         pending=None, message_id=message_id, status='Updated', errors=0, due=self.clock()+watch['interval'])
            self.save()
        except SessionExpired as exc:
            watch['status'] = 'Waiting for login refresh and /ws session recheck'
            watch['due'] = self.clock()
            self.save()
            await self.client.session_expired(str(exc), watch['channel'])
        except asyncio.CancelledError:
            watch['due'] = self.clock()+watch['interval']
            watch['status'] = 'Check interrupted; next scheduled attempt will reconcile saved delivery'
            self.save()
            raise
        except Exception as exc:
            # Never print provider response bodies, cookies, URLs with credentials, or private standings.
            reason = str(exc) if isinstance(exc, ArchiveError) else f'Leaderboard check failed ({type(exc).__name__}).'
            watch['errors'] += 1
            watch['status'] = reason[:600]
            watch['due'] = self.clock()+max(watch['interval'], min(3600, 60*2**min(watch['errors'], 6)))
            self.save()
            LOG.warning('Leaderboard update unavailable (%s).', type(exc).__name__)
            # One notice per failure episode. No stale snapshot is passed off as a new reading.
            if watch['errors'] == 1:
                try:
                    channel = await self.destination(watch)
                    await channel.send('**WS leaderboard update unavailable**\n'+reason[:600]+
                                       '\nPrevious standings retain their original timestamp. I will retry automatically. '
                                       'Use `/ws leaderboard action:status` for details.', allowed_mentions=discord.AllowedMentions.none())
                except (ArchiveError, discord.HTTPException):
                    pass

    async def command(self, interaction, link=None, interval=None, action='start', team=''):
        key = str(interaction.channel_id)
        watch = self.watches.get(key)
        if action == 'status':
            message = ('No leaderboard is configured here.' if not watch else
                f"**WS leaderboard — {watch['state']}**\n<{watch['url']}>\nEvery {watch['interval']//60} minutes\n"
                f"{safe(watch['status'], 650)}" +
                (f"\nNext attempt: <t:{int(watch['due'])}:R>" if watch['state']=='active' else '\nAutomatic updates are stopped.') +
                (f"\nLast report: https://discord.com/channels/{watch['guild']}/{watch['channel']}/{watch['message_id']}" if watch.get('message_id') else ''))
            await interaction.response.send_message(message, ephemeral=True)
            return
        if self.client.busy():
            raise ArchiveError('A scan or check is running. Wait for it to finish before changing leaderboard watches.')
        if action == 'stop':
            if not watch:
                raise ArchiveError('No leaderboard is configured in this channel.')
            watch['state'] = 'stopped'
            self.save()
            await interaction.response.send_message('Leaderboard updates stopped in this channel. Existing reports were preserved.', ephemeral=True)
            return
        if action == 'now':
            if not watch:
                raise ArchiveError('Configure a leaderboard with link: and time: first.')
            # A stopped watch stays stopped; this is a single explicit refresh.
            await interaction.response.defer(ephemeral=True)
            await self.refresh(watch)
            await interaction.followup.send(watch['status'], ephemeral=True)
            return
        if not link or not interval:
            raise ArchiveError('Use /ws leaderboard link:<event leaderboard URL> time:10m in the channel for updates. '
                               'Use action:status, action:now or action:stop to manage it.')
        await interaction.response.defer(ephemeral=True)
        candidate = dict(channel=interaction.channel_id, guild=interaction.guild_id, owner=interaction.user.id)
        channel = await self.destination(candidate)
        if self.client.busy():
            raise ArchiveError('Another scan or check started. Try again after it finishes.')
        watch = self.configure(channel, interaction.user.id, link, interval, team)
        await self.refresh(watch)
        await interaction.followup.send(f"Leaderboard saved here: every {watch['interval']//60} minutes. {watch['status']}\n"
                                       'Use `/ws leaderboard action:stop` to stop updates.', ephemeral=True)

    async def refresh(self, watch):
        if self.client.busy():
            raise ArchiveError('A scan or check is already running.')
        if self.store.get('auth_invalid', False) and not watch.get('pending'):
            watch['status'] = 'Waiting for login refresh and /ws session recheck'
            self.save()
            return
        self.client.scan_phase = 'leaderboard'
        task = self.client.scan_task = asyncio.create_task(self.run(watch))
        try:
            await task
        except asyncio.CancelledError:
            if getattr(self.client, 'ws_closing', False):
                raise
        finally:
            if self.client.scan_task is task:
                self.client.scan_phase = 'idle'
