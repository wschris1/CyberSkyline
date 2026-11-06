"""One-time recovery after a host transfer loses the private archive database.

Reads the configured GitHub archive, authorized source pages, and bot-authored
Discord archive messages. Never sends, edits, deletes, or submits remote content.
Run only while the regular bot is stopped; restore a database backup instead when
one exists. The private recovery report contains counts, never tokens or answers.
"""

import asyncio
import json
import os
from pathlib import Path
import re
import subprocess
import sys


class RecoveryError(ValueError):
    """Only static, credential-free recovery diagnostics belong in this type."""


def unique_messages(messages, bot_id):
    """Reject ambiguous delivery rather than choosing one of duplicate posts."""
    found = {}
    for message in messages:
        if message.author.id != bot_id:
            continue
        for embed in message.embeds:
            tag = embed.footer.text or ''
            if not re.fullmatch(r'(?:WS|NCL) archive [0-9a-f]{32}', tag):
                continue
            tag = tag.replace('NCL archive ', 'WS archive ', 1)
            if tag in found and found[tag].id != message.id:
                raise RecoveryError('Duplicate archive markers require manual reconciliation.')
            found[tag] = message
    return found


def record_post(store, key, message, file_path=None, filename=None):
    from bots.skyline_archive.storage import digest
    old = store.one('SELECT * FROM posts WHERE key=?', (key,))
    if old and (old['channel_id'], old['message_id']) != (message.channel.id, message.id):
        raise RecoveryError('Existing post mapping conflicts with recovered message.')
    description = message.embeds[0].description or ''
    with store.db:
        store.db.execute('''INSERT OR REPLACE INTO posts VALUES(?,?,?,?,?,?)''',
                         (key, message.channel.id, message.id,
                          digest([description, str(file_path or ''), filename]),
                          'active', message.created_at.isoformat()))


def recover_parts(store, key, markers, required=True, source_key=None):
    from bots.skyline_archive.discord_archive import marker
    source_key = source_key or key
    if source_key != key:
        live = markers.get(marker(source_key + '/part0'))
        legacy = markers.get(marker(key + '/part0'))
        if live and legacy and live.id != legacy.id:
            raise RecoveryError('Both positional and source-ID posts exist; reconcile before recovery.')
        if legacy and not live:
            source_key = key
    found = [markers[marker(f'{source_key}/part{i}')] for i in range(100)
             if marker(f'{source_key}/part{i}') in markers]
    if required and not found:
        raise RecoveryError('An expected archive message was not found; recovery stopped.')
    # Never silently discard a gap or a long continuation chain.
    for i, message in enumerate(found):
        if markers.get(marker(f'{source_key}/part{i}')) is not message:
            raise RecoveryError('Archive continuation sequence is incomplete.')
        record_post(store, f'{key}/part{i}', message)
    if marker(f'{source_key}/part100') in markers:
        raise RecoveryError('Archive continuation limit reached.')
    return found


def restore_verifications(store, question_key, messages, bot_id):
    """Recover exact displayed answers; missing submitter identity stays unknown."""
    count = 0
    pattern = re.compile(r'^\*\*(Verified correct|Verified incorrect|Inconclusive|Verification error)'
                         r' — Q\d+\*\*\n(`{3,})json\n(.*?)\n\2\n'
                         r'\*\*Method:\*\* (.*?)\n(.*?)\nNo answer was submitted to Cyber Skyline\.', re.S)
    for message in messages:
        if message.author.id != bot_id:
            continue
        match = pattern.match(message.content)
        if not match:
            continue
        try:
            proposed = json.loads(match[3])
        except ValueError:
            continue
        if not isinstance(proposed, str):
            continue
        recovery_key = 'recovered-verification/' + str(message.id)
        if store.get(recovery_key):
            continue
        # Discord channel.send results do not retain the invoking interaction's
        # user. Zero explicitly means unknown; do not invent an owner identity.
        unescape = lambda value: re.sub(r'\\([\\`*_{}\[\]()#+.!|>~-])', r'\1', value)
        with store.db:
            store.db.execute('''INSERT INTO verifications(question_key,answer,user_id,created,method,outcome,evidence)
                VALUES(?,?,0,?,?,?,?)''', (question_key, proposed, message.created_at.isoformat(),
                unescape(match[4]), match[1], unescape(match[5]) +
                '\nRecovered from the original Discord result. Submitting user was not recoverable.'))
            store.put(recovery_key, True)
        count += 1
    return count


async def history(channel, limit=2000):
    rows = [message async for message in channel.history(limit=limit + 1, oldest_first=True)]
    if len(rows) > limit:
        raise RecoveryError('History limit reached; recovery stopped without posting.')
    return rows


def upload_note(row, message):
    """A matching bot footer already binds this upload to the source SHA-256.

    Discord may transform an image, including its byte size. Preserve that upload
    while keeping the freshly downloaded original as the verification evidence.
    """
    if len(message.attachments) != 1 or message.attachments[0].filename != row['name']:
        raise RecoveryError('Recovered file post is missing its expected attachment.')
    if message.attachments[0].size != row['size']:
        return 'Discord upload byte size differs from the source; verification uses the cached original.'
    return None


async def recover(settings):
    import aiohttp
    import discord
    from bots.skyline_archive.attachments import Attachments
    from bots.skyline_archive.discord_archive import marker
    from bots.skyline_archive.github import GitHub
    from bots.skyline_archive.scanner import Scanner
    from bots.skyline_archive.storage import Store

    store = Store(settings.state_dir)
    try:
        if store.get('host-recovery-complete'):
            print('Recovery already completed; switch the startup file back to bot.py.', flush=True)
            return
        if store.one('SELECT key FROM questions WHERE message_id IS NOT NULL LIMIT 1') and not store.get('host-recovery-in-progress'):
            raise RecoveryError('A linked archive database already exists. Restore its backup, not this tool.')
        store.put('host-recovery-in-progress', True)
        store.save_settings(dict(enabled=False, archive_enabled=False, default_preview=True, ai_enabled=False))
        attachments = Attachments(store)
        async with aiohttp.ClientSession() as session:
            count = await GitHub(settings, session).index_into(store)
        print(f'Indexed {count} archived questions; no remote content changed.', flush=True)
        entries = [dict(url=row['source'], event=row['event'], category=row['category'], title=row['title'],
                        season=row['season'], competition=row['competition'], level=row['level'])
                   for row in store.rows('SELECT * FROM challenges ORDER BY key')]
        if not entries:
            raise RecoveryError('No archived challenge identities are available for recovery.')

        async def cache(challenge, context):
            store.upsert_challenge(challenge)
            for ref in challenge.attachment_refs:
                await attachments.fetch(challenge, ref, context)

        result = await Scanner(settings, print).collect(catalog=entries, on_challenge=cache)
        if result.errors or len(result.challenges) != len(entries):
            raise RecoveryError('Source recovery was incomplete. Refresh login or review source access before retrying.')
        print(f'Read {len(result.challenges)} source challenges and cached available files.', flush=True)
        async with discord.Client(intents=discord.Intents(guilds=True, message_content=settings.message_content)) as client:
            await client.login(settings.discord_token)
            guild = await client.fetch_guild(settings.guild_id)
            channels = await guild.fetch_channels()
            # Only bot-created archive channels with the documented topic qualify.
            candidates = [c for c in channels if isinstance(c, discord.TextChannel)
                          and (c.topic or '').startswith(('WS: ','NCL TRACKER: '))]
            messages = []
            for channel in candidates:
                messages.extend(await history(channel))
            markers = unique_messages(messages, client.user.id)
            linked, files, verifications, transformed = 0, 0, 0, 0
            for index, challenge in enumerate(result.challenges, 1):
                print(f'Relinking challenge {index}/{len(result.challenges)}.', flush=True)
                parents = recover_parts(store, 'challenge/' + challenge.key, markers)
                channel = parents[0].channel
                if channel.guild.id != settings.guild_id or channel.category_id is None:
                    raise RecoveryError('Archive category identity could not be recovered.')
                row = store.one('SELECT level FROM challenges WHERE key=?', (challenge.key,))
                scope = challenge.category.casefold()
                for kind, name, ident in [('category', scope, channel.category_id),
                                          ('channel', scope + '/' + row['level'], channel.id)]:
                    existing = store.mapping(kind, name)
                    if existing is not None and existing != ident:
                        raise RecoveryError('Conflicting archive destinations require manual reconciliation.')
                    store.map(kind, name, ident)
                for question in store.rows('SELECT * FROM questions WHERE challenge_key=? ORDER BY number', (challenge.key,)):
                    # GitHub imports have positional row keys. Original Discord
                    # markers used live source IDs; keep the stored row key stable.
                    source_key = challenge.key + '/' + challenge.question_ids[question['number'] - 1]
                    parent = recover_parts(store, 'question/' + question['key'], markers,
                                           source_key='question/' + source_key)[0]
                    thread_ids = []
                    for embed in parent.embeds:
                        for field in embed.fields:
                            if field.name == 'Discussion':
                                match = re.fullmatch(r'\[Open question thread\]\(https://discord.com/channels/(\d+)/(\d+)\)', field.value)
                                if match and int(match[1]) == settings.guild_id:
                                    thread_ids.append(int(match[2]))
                    if len(set(thread_ids)) > 1:
                        raise RecoveryError('Ambiguous question discussion link.')
                    thread = await client.fetch_channel(thread_ids[0] if thread_ids else parent.id)
                    if not isinstance(thread, discord.Thread) or thread.guild.id != settings.guild_id or thread.parent_id != parent.channel.id:
                        raise RecoveryError('Question thread belongs to an unexpected destination.')
                    thread_messages = await history(thread)
                    recover_parts(store, 'thread/' + question['key'], unique_messages(thread_messages, client.user.id),
                                  source_key='thread/' + source_key)
                    store.link_question(question['key'], parent.channel.id, parent.id, thread.id)
                    verifications += restore_verifications(store, question['key'], thread_messages, client.user.id)
                    linked += 1
                print(f'Relinked {linked}/{count} question threads.', flush=True)
                for row in store.rows('SELECT * FROM attachments WHERE challenge_key=?', (challenge.key,)):
                    if not row.get('sha256'):
                        continue
                    key = 'file/' + row['key'] + '/' + row['sha256']
                    message = markers.get(marker(key))
                    if message:
                        note = upload_note(row, message)
                        if note:
                            transformed += 1
                            print(note, flush=True)
                        record_post(store, key, message, row['path'], row['name'])
                        store.attachment(row['key'], status='uploaded', message_id=message.id,
                                         channel_id=message.channel.id, error=note)
                        files += 1
                store.synced(challenge.key)

        if linked != count:
            raise RecoveryError('Question count differs from the GitHub archive; recovery needs review.')
        if store.db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or store.rows('PRAGMA foreign_key_check'):
            raise RecoveryError('Recovered database did not pass integrity checks.')
        store.put('auth_invalid', False)
        store.put('host-recovery-complete', True)
        store.put('host-recovery-in-progress', False)
        report = dict(challenges=len(result.challenges), questions=linked,
                      posts=store.one('SELECT count(*) AS n FROM posts')['n'],
                      mappings=store.one('SELECT count(*) AS n FROM mappings')['n'],
                      recovered_uploads=files, recovered_verifications=verifications,
                      discord_upload_size_differences=transformed,
                      scheduled_scans=False, default_preview=True,
                      limitations='Original scan history and missing settings/watches cannot be reconstructed. '
                                   'Recovered verification submitters are unknown (user_id=0). '
                                   'Long verification reports stored only in attachments are left in Discord.')
        path = settings.state_dir / 'host-recovery-report.json'
        path.write_text(json.dumps(report, indent=2), encoding='utf-8')
        path.chmod(0o600)
        store.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        print('RECOVERY COMPLETE: ' + json.dumps(report), flush=True)
    finally:
        store.close()


def main():
    import bot as loader
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parent
    app = loader.install_source(root)
    config, state = loader.prepare_private(root)
    load_dotenv(config, override=True)
    os.environ.setdefault('SKYLINE_STATE_DIR', str(state))
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(root / 'browser-cache'))
    sys.path.insert(0, str(app))
    subprocess.run([sys.executable, '-m', 'playwright', 'install', '--only-shell', 'chromium'], check=True, timeout=600)
    loader.prepare_browser_libraries(root)
    asyncio.run(loader.browser_check())
    from bots.skyline_archive.__main__ import InstanceLock
    from bots.skyline_archive.settings import load_settings
    with InstanceLock(state):
        asyncio.run(recover(load_settings()))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        if isinstance(exc, RecoveryError):
            print(str(exc), flush=True)
        # HTTP exception messages can contain request details; emit types only.
        print(f'RECOVERY STOPPED ({type(exc).__name__}). No remote archive content was changed. '
              'Review access, source availability, and existing archive markers before retrying.', flush=True)
        raise SystemExit(1)
