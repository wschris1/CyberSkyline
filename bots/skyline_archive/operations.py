"""Owner operations that never submit answers or publish supplemental evidence to Git."""

import asyncio
import io
import time
from urllib.parse import quote

import discord

from .core import ArchiveError, SessionExpired
from .github import GitHub
from .scanner import Scanner
from .storage import now
from .progress import Progress, ProgressMessage


def question_here(client, interaction):
    question = client.store.question(thread_id=interaction.channel_id)
    if not question:
        raise ArchiveError('Run this command inside an archived question thread.')
    permissions = interaction.channel.permissions_for(interaction.user)
    if not permissions.view_channel or not permissions.read_message_history:
        raise ArchiveError('You cannot access this question thread.')
    return question


async def evidence(client, interaction, file=None, message_id=None):
    question = question_here(client,interaction)
    await interaction.response.defer(ephemeral=True)
    if file is not None and message_id is not None:
        raise ArchiveError('Choose a file or a message ID, not both.')
    if file is not None:
        uploads = [file]
        origin = None
    else:
        if message_id:
            if not message_id.isdecimal():
                raise ArchiveError('Provide the numeric message ID from this thread.')
            origin = await interaction.channel.fetch_message(int(message_id))
        else:
            origin = next(iter([m async for m in interaction.channel.history(limit=100)
                           if m.author.id == interaction.user.id and m.attachments]),None)
        if not origin or origin.author.id != interaction.user.id or origin.author.bot:
            raise ArchiveError('Upload evidence in this thread first, or use the file option. Only your own messages are imported.')
        uploads = origin.attachments
        if not uploads:
            raise ArchiveError('That message has no attachments.')
    rows = []
    for upload in uploads[:10]:
        row = await client.attachments.evidence(question,upload,interaction.user.id,interaction.channel_id,
                                                origin.id if origin else None)
        rows.append(f"{discord.utils.escape_markdown(row['name'])}: {row['status']}"+(f" — {row['error']}" if row['error'] else ''))
    await interaction.followup.send(('**Evidence for Q'+str(question['number'])+'**\n'+'\n'.join(rows)+
        '\nPrivate files are available to `/skyline verify`, `/skyline hint`, and `/skyline explain`. They are not uploaded to GitHub.')[:1950],ephemeral=True)


async def assistance(client, interaction, mode):
    question = question_here(client,interaction)
    await interaction.response.defer(ephemeral=True)
    report = await client.verifier.explain(question,mode)
    body = f'**AI {mode} — Q{question["number"]}**\nSuggestions, not a verified answer.\n\n{report["evidence"]}'
    with client.store.db:
        client.store.db.execute('INSERT INTO assistance(question_key,user_id,mode,created,report) VALUES(?,?,?,?,?)',
            (question['key'],interaction.user.id,mode,now(),body))
    if len(body) <= 1950:
        await interaction.channel.send(body,allowed_mentions=discord.AllowedMentions.none())
    else:
        with discord.File(io.BytesIO(body.encode()),filename=mode+'-report.txt') as attachment:
            await interaction.channel.send(f'AI {mode} for Q{question["number"]} is attached. Suggestions, not verified correctness.',file=attachment)
    await interaction.followup.send('Assistance posted in this question thread. Verification status was not changed.',ephemeral=True)


async def health(client, interaction, test_ai=False):
    if client.busy():
        raise ArchiveError('Wait for the active scan or pause it before running the health check.')
    await interaction.response.defer(ephemeral=True)
    async def check():
        rows = []
        try:
            await Scanner(client.settings).validate_session()
            client.store.put('auth_invalid',False); client.store.put('auth_alert_sent',False)
            rows.append('Cyber Skyline: login validated')
        except SessionExpired as exc:
            await client.session_expired(str(exc),interaction.channel_id)
            rows.append('Cyber Skyline: login expired; refresh and recheck')
        except Exception:
            rows.append('Cyber Skyline: network/page check failed; login state unchanged')
        try:
            github = GitHub(client.settings,client.http_session)
            repo = await github.request('GET','')
            await github.request('GET','/git/ref/heads/'+quote(client.settings.branch,safe=''))
            access = 'read access confirmed; token reports push access' if repo.get('permissions',{}).get('push') else 'read access confirmed; write access untested'
            rows.append('GitHub: '+access+' (branch rules still apply)')
        except ArchiveError as exc:
            rows.append('GitHub: '+str(exc))
        prefs = client.preferences.effective()
        guild = client.get_guild(client.settings.guild_id)
        needed = ('manage_channels','manage_threads','create_public_threads','send_messages_in_threads','attach_files')
        missing = [p for p in needed if not guild or not getattr(guild.me.guild_permissions,p,False)]
        rows.append('Discord archive permissions: '+(', '.join(missing)+' missing' if missing else 'server permissions present'))
        for label,key in (('Progress destination','archive_hub'),('Notifications','notification_channel')):
            try:
                channel = await client.archive.channel(prefs[key]) if prefs[key] else None
                required = ('view_channel','send_messages','read_message_history','embed_links')
                valid = channel and all(getattr(channel.permissions_for(guild.me),p,False) for p in required)
                rows.append(label+(': ready' if valid else ': missing or permissions insufficient'))
            except (ArchiveError,discord.HTTPException):
                rows.append(label+': unavailable')
        rows.append('OpenAI: '+(await client.ai.health() if test_ai else client.ai.status()+'; use test_ai:true to test'))
        rows.append('Private cache: '+str(round(await asyncio.to_thread(client.attachments.usage)/1048576,1))+f" / {prefs['cache_mb']} MiB; file limit {prefs['max_file_mb']} MiB")
        rows.append('Last successful archive: '+str(client.store.get('last_success','none recorded')))
        if client.store.get('schedule_hold',False):
            scheduled = 'paused by scan control; use /skyline resume'
        elif client.store.get('auth_invalid',False):
            scheduled = 'blocked until login is refreshed'
        elif prefs['enabled']:
            due = max(time.time(),client.store.get('last_scheduled',0)+prefs['frequency']*60)
            scheduled = f'<t:{int(due)}:R> (every {prefs["frequency"]} minutes)'
        else:
            scheduled = 'disabled'
        rows.append('Next scheduled check: '+scheduled)
        return '\n'.join(rows)
    client.scan_phase='checking login'
    client.scan_task=asyncio.create_task(check())
    try:
        text = await client.scan_task
    finally:
        client.scan_phase='idle'
    await interaction.followup.send(('**NCL TRACKER health**\n'+text)[:1950],ephemeral=True)


async def reorganize(client, interaction, preview=True):
    if client.busy():
        raise ArchiveError('Wait for the scan or pause it before reorganizing.')
    if not client.preferences.effective()['archive_enabled']:
        raise ArchiveError('Enable the Discord archive in /skyline settings first.')
    keys = client.store.rows('SELECT DISTINCT challenge_key FROM questions WHERE message_id IS NOT NULL')
    if preview:
        missing = sum(not client.store.mapping('challenge-channel',r['challenge_key']) for r in keys)
        await interaction.response.send_message(f'{len(keys)} existing challenges; {missing} need challenge channels. Existing discussions will remain linked. Run `/skyline reorganize preview:false` to apply.',ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    async def work():
        progress = Progress(total=len(keys),state='reorganizing archive')
        client.progress=progress; client.scan_preview=False
        message = await interaction.channel.send(progress.render())
        live = ProgressMessage(message,progress,False); live.start()
        try:
            for item in keys:
                c=client.store.snapshot(item['challenge_key'])
                try:
                    await client.archive.publish([c],progress)
                    progress.new+=1
                except (ArchiveError,discord.HTTPException):
                    progress.failed+=1
                progress.processed+=1
                if client.pause_requested:
                    progress.update(state='paused',detail='Reorganization paused safely. Rerun /skyline reorganize preview:false to continue; saved channels and threads will be reused.')
                    return
            progress.update(state='completed with errors' if progress.failed else 'completed',
                detail='Existing discussions retained and linked. Rerun reorganize to retry any incomplete migrations.')
        finally:
            if progress.finished is None:
                progress.update(state='interrupted',detail='Rerun reorganize; saved IDs prevent duplicate channels and threads.')
            await live.finish()
    client.pause_requested=False
    client.scan_phase='publishing'; client.scan_task=asyncio.create_task(work())
    client.scan_task.add_done_callback(client.scan_finished)
    await interaction.followup.send('Reorganizing existing archives into challenge channels. Progress will update here.',ephemeral=True)
