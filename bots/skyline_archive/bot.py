"""Owner-managed archive workflow: scans, persistent Discord archive and evidence checks."""

import asyncio
from datetime import datetime, timezone
import io
import json
import logging
import re
import time
from typing import Literal

import aiohttp
import discord
from discord import app_commands

from .core import ArchiveError, SessionExpired, skyline_url, level_and_title
from .github import GitHub, ApiError
from .scanner import Scanner
from .survey import SurveyManager, SurveyProbe
from .storage import Store, now
from .jobs import Jobs
from . import operations
from . import cleanup_ui
from .cleanup import Cleanup
from .preferences import Preferences
from .attachments import Attachments
from .discord_archive import DiscordArchive
from .progress import Progress, ProgressMessage
from .verification import Verifier, select_answer
from .ai_verification import OpenAIAssistant
from .ui import Picker, SettingsView, SearchView, AnswerPicker, FailuresView
from .workflows import DiscordPipeline, catalog_entry, github_target, mapped_archives, validate_parents

LOG=logging.getLogger(__name__)


async def owner_check(client,interaction):
    if interaction.guild_id!=client.settings.guild_id or interaction.user.id not in client.settings.owners:
        await interaction.response.send_message('This bot is restricted to its configured owners and server.',ephemeral=True)
        return False
    return True


class SessionCommands(app_commands.Group):
    def __init__(self,client):
        super().__init__(name='session',description='Check the saved Cyber Skyline login.')
        self.client=client

    async def interaction_check(self,interaction):
        return await owner_check(self.client,interaction)

    @app_commands.command(name='recheck',description='Validate a refreshed login and unblock scheduled scans.')
    async def recheck(self,interaction:discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if self.client.busy():
            await interaction.followup.send('A scan or discovery is running. Stop it before rechecking the session.',ephemeral=True)
            return
        async def check():
            try:
                await Scanner(self.client.settings).validate_session()
            except SessionExpired as exc:
                await self.client.session_expired(str(exc),interaction.channel_id)
                return str(exc)
            except Exception:
                return 'Session check hit a network or page error. Existing authentication state was retained; try again.'
            self.client.store.put('auth_invalid',False)
            self.client.store.put('auth_alert_sent',False)
            return 'Cyber Skyline login validated. Manual and scheduled scans can run again.'
        self.client.scan_task=asyncio.create_task(check())
        self.client.scan_phase='checking login'
        message=await self.client.scan_task
        self.client.scan_phase='idle'
        await interaction.followup.send(message,ephemeral=True)


class SkylineCommands(app_commands.Group):
    def __init__(self,client):
        super().__init__(name='skyline',description='Archive challenge questions and watch for surveys.',guild_only=True)
        self.client=client
        self.add_command(SessionCommands(client))

    async def interaction_check(self,interaction):
        return await owner_check(self.client,interaction)

    async def on_error(self,interaction,error):
        original=getattr(error,'original',error)
        message=str(original) if isinstance(original,ArchiveError) else 'Command failed. Check the bot host and configuration.'
        if interaction.response.is_done():
            await interaction.followup.send(message[:1900],ephemeral=True)
        else:
            await interaction.response.send_message(message[:1900],ephemeral=True)

    @app_commands.command(name='sync',description='Scan one Cyber Skyline event and archive its questions.')
    @app_commands.describe(event_url='The event overview URL (/world/...).',preview='Override the saved default; no archive writes when true.')
    async def sync(self,interaction:discord.Interaction,event_url:str|None=None,preview:bool|None=None):
        target=skyline_url(event_url or self.client.settings.event_url)
        await self.client.launch_interaction(interaction,event_url=target,preview=preview)

    @app_commands.command(name='sync-all',description='Scan every event still accessible on your Competition dashboard.')
    @app_commands.describe(preview='Override the saved default; no archive writes when true.')
    async def sync_all(self,interaction:discord.Interaction,preview:bool|None=None):
        await self.client.launch_interaction(interaction,all_events=True,preview=preview)

    async def scoped_scan(self,interaction,event_url,all_events,preview,workflow):
        if all_events and event_url:
            raise ArchiveError('Choose either one event URL or all_events:true.')
        target=None if all_events else skyline_url(event_url or self.client.settings.event_url)
        await self.client.launch_interaction(interaction,event_url=target,all_events=all_events,
                                             preview=preview,workflow=workflow)

    @app_commands.command(name='scan-discord',description='Fast scan: collect challenges and build Discord channels and threads as they arrive.')
    @app_commands.describe(event_url='One event URL; otherwise use the configured event.',all_events='Scan every accessible event instead.',
                           preview='Show the plan without creating archive content.')
    async def scan_discord(self,interaction:discord.Interaction,event_url:str|None=None,all_events:bool=False,preview:bool|None=None):
        await self.scoped_scan(interaction,event_url,all_events,preview,'discord')

    @app_commands.command(name='scan-both',description='Build the Discord archive first, then export collected prompts to GitHub.')
    @app_commands.describe(event_url='One event URL; otherwise use the configured event.',all_events='Scan every accessible event instead.',
                           preview='Show the plan without creating archive content or GitHub files.')
    async def scan_both(self,interaction:discord.Interaction,event_url:str|None=None,all_events:bool=False,preview:bool|None=None):
        await self.scoped_scan(interaction,event_url,all_events,preview,'both')

    @app_commands.command(name='export-github',description='Export saved prompts from mapped Discord archives; never read answers or rescan Skyline.')
    async def export_github(self,interaction:discord.Interaction,channel:discord.TextChannel|None=None,
                            season:str|None=None,competition:str|None=None,category:str|None=None,
                            difficulty:str|None=None,preview:bool|None=None):
        if channel and channel.guild.id!=self.client.settings.guild_id:
            raise ArchiveError('Choose an archive channel in the configured server.')
        await self.client.launch_interaction(interaction,workflow='github',preview=preview,
            archive_channel_id=channel.id if channel else 0,
            scope=dict(season=season,competition=competition,category=category,level=difficulty))

    @app_commands.command(name='stop',description='Stop collecting or posting; preserve completed work. GitHub commits finish safely.')
    async def stop(self,interaction:discord.Interaction):
        await interaction.response.send_message(self.client.stop_sync(),ephemeral=True)

    @app_commands.command(name='pause',description='Pause the scan at a safe checkpoint and hold scheduled attempts.')
    async def pause(self,interaction:discord.Interaction):
        await interaction.response.send_message(self.client.pause_sync(),ephemeral=True)

    @app_commands.command(name='resume',description='Resume the saved scan after pause/restart and release the schedule hold.')
    async def resume(self,interaction:discord.Interaction):
        await self.client.resume_interaction(interaction)

    @app_commands.command(name='retry-failed',description='Retry failed pages or publications from the latest saved scan.')
    async def retry_failed(self,interaction:discord.Interaction):
        await self.client.resume_interaction(interaction,retry=True)

    @app_commands.command(name='failures',description='Show saved failed challenges, reasons and suggested fixes; works during scans.')
    @app_commands.describe(scan_id='Optional saved scan number; defaults to the latest scan with failures.')
    async def failures(self,interaction:discord.Interaction,scan_id:app_commands.Range[int,1]|None=None):
        view=FailuresView(self.client,interaction.user.id,scan_id)
        await interaction.response.send_message(view.render(),view=view,ephemeral=True)

    @app_commands.command(name='health',description='Check source login, GitHub, Discord permissions, storage and optionally AI.')
    async def health(self,interaction:discord.Interaction,test_ai:bool=False):
        await operations.health(self.client,interaction,test_ai)

    @app_commands.command(name='evidence',description='Attach your uploaded file or latest upload in this thread as question evidence.')
    async def evidence(self,interaction:discord.Interaction,file:discord.Attachment|None=None,message_id:str|None=None):
        await operations.evidence(self.client,interaction,file,message_id)

    @app_commands.command(name='hint',description='Ask for an evidence-guided hint without supplying an answer.')
    async def hint(self,interaction:discord.Interaction):
        await operations.assistance(self.client,interaction,'hint')

    @app_commands.command(name='explain',description='Explain an evidence-based solving approach without verifying an answer.')
    async def explain(self,interaction:discord.Interaction):
        await operations.assistance(self.client,interaction,'explain')

    @app_commands.command(name='reorganize',description='Create challenge channels and question threads; retain and link old discussions.')
    async def reorganize(self,interaction:discord.Interaction,preview:bool=True):
        await operations.reorganize(self.client,interaction,preview)

    @app_commands.command(name='status',description='Show scan progress, result, and automatic-sync settings.')
    async def status(self,interaction:discord.Interaction):
        prefs=self.client.preferences.effective()
        schedule=f"Every {prefs['frequency']} minutes" if prefs['enabled'] else 'Off'
        mode=('**Mode:** '+('Preview (no uploads)' if self.client.scan_preview else 'Scan and upload')+'\n') if self.client.busy() else ''
        if self.client.progress:
            archive=self.client.progress.render(self.client.scan_preview)
        else:
            archive=self.client.archive_status
        auth='Waiting for login refresh; run `/skyline session recheck`.' if self.client.store.get('auth_invalid',False) else 'No known login failure.'
        await interaction.response.send_message((f'{mode}**Archive:** {archive}\n**Automatic sync:** {schedule}\n**Session:** {auth}\n'
            f'**Repository:** https://github.com/{self.client.settings.repository}')[:1950],ephemeral=True)

    @app_commands.command(name='pick',description='Discover accessible competitions and choose a scope interactively.')
    async def pick(self,interaction:discord.Interaction,destination:Literal['discord','both']='discord'):
        if self.client.busy():
            raise ArchiveError('A scan or discovery is already running.')
        if self.client.store.get('auth_invalid',False):
            raise ArchiveError('Refresh the saved login and run /skyline session recheck first.')
        await interaction.response.defer(ephemeral=True)
        self.client.start_sync(all_events=True,preview=True,channel=interaction.channel,catalog_only=True,
                               owner=interaction.user.id,workflow=destination)
        await interaction.followup.send('Discovering accessible competitions. The progress message will contain your picker when ready.',ephemeral=True)

    @app_commands.command(name='search',description='Search locally archived questions you can access.')
    async def search(self,interaction:discord.Interaction,keyword:str,season:str|None=None,competition:str|None=None,
                     category:str|None=None,difficulty:str|None=None):
        await interaction.response.defer(ephemeral=True)
        view=SearchView(self.client,interaction.user.id,keyword,dict(season=season,competition=competition,category=category,level=difficulty))
        await interaction.followup.send(await view.render(interaction.user),view=view,ephemeral=True)

    @app_commands.command(name='reindex',description='Index older GitHub imports locally without reposting or creating threads.')
    async def reindex(self,interaction:discord.Interaction):
        if self.client.busy():
            raise ArchiveError('Wait for the current scan before rebuilding the index.')
        await interaction.response.defer(ephemeral=True)
        async def work():
            return await GitHub(self.client.settings,self.client.http_session).index_into(self.client.store)
        self.client.scan_phase='indexing'
        self.client.scan_task=asyncio.create_task(work())
        try:
            count=await self.client.scan_task
        finally:
            self.client.scan_phase='idle'
        await interaction.followup.send(f'Indexed {count} older questions. No Discord archive content was posted.',ephemeral=True)

    @app_commands.command(name='settings',description='Manage scan defaults, archive destinations, notifications and mappings.')
    async def settings(self,interaction:discord.Interaction):
        view=SettingsView(self.client,interaction.user.id)
        await interaction.response.send_message(view.summary(),view=view,ephemeral=True)

    @app_commands.command(name='verify',description='Check an answer against evidence in this question thread; never submit it.')
    async def verify(self,interaction:discord.Interaction,answer:str|None=None):
        question=self.client.store.question(thread_id=interaction.channel_id)
        if not question:
            raise ArchiveError('Run /skyline verify inside a mapped question thread.')
        if answer is not None:
            await self.client.verify_answer(interaction,question,answer)
            return
        await interaction.response.defer(ephemeral=True)
        latest=self.client.store.one('SELECT created FROM verifications WHERE question_key=? AND user_id=? ORDER BY id DESC LIMIT 1',
                                     (question['key'],interaction.user.id))
        since=datetime.fromisoformat(latest['created']) if latest else None
        messages=[m async for m in interaction.channel.history(limit=100)]
        selected,candidates=select_answer(messages,interaction.user.id,since)
        if selected is not None and getattr(self.client.settings,'message_content',False):
            await self.client.verify_answer(interaction,question,selected)
        else:
            view=AnswerPicker(self.client,interaction.user.id,question,candidates)
            await interaction.followup.send('Choose your answer message or provide its exact text. If message content access is disabled, use the answer field.',view=view,ephemeral=True)

    @app_commands.command(name='watch-survey',description='Ping you here when a survey website actually loads a usable form.')
    @app_commands.describe(challenge_url='The Survey challenge URL (/module/.../.../...).',
        survey_url='Optional actual survey link, useful while the challenge link is blank.',ready_text='Optional text required on the usable form.')
    async def watch_survey(self,interaction:discord.Interaction,challenge_url:str,survey_url:str='',ready_text:str=''):
        if interaction.channel_id is None:
            raise ArchiveError('Run this command in the channel where you want the ping.')
        key=self.client.surveys.add(challenge_url,survey_url,ready_text,interaction.user.id,interaction.channel_id,interaction.guild_id)
        await interaction.response.send_message(f'Watch `{key}` saved. I will ping you here after the form is ready on two checks. Use `/skyline survey-status` for progress.',ephemeral=True)

    @app_commands.command(name='survey-status',description='Show your saved survey watches and last readiness checks.')
    async def survey_status(self,interaction:discord.Interaction):
        rows=[f"`{key}` — **{item['delivery']}**: {item['status']}" for key,item in self.client.surveys.watches.items() if item['owner_id']==interaction.user.id]
        await interaction.response.send_message('\n'.join(rows)[:1950] or 'You have no saved survey watches.',ephemeral=True)

    @app_commands.command(name='unwatch-survey',description='Remove one of your survey watches, including a finished watch.')
    async def unwatch_survey(self,interaction:discord.Interaction,watch_id:str):
        watch=self.client.surveys.watches.get(watch_id)
        if not watch or watch['owner_id']!=interaction.user.id:
            raise ArchiveError('That watch was not found for your account.')
        del self.client.surveys.watches[watch_id]
        self.client.surveys.save()
        await interaction.response.send_message(f'Removed watch `{watch_id}`.',ephemeral=True)


class CleanupCommands(app_commands.Group):
    # The existing /skyline group already uses Discord's 25-child limit.
    def __init__(self,client):
        super().__init__(name='skyline-cleanup',description='Remove Discord archives only after verifying their GitHub question copies.',guild_only=True)
        self.client=client

    interaction_check=SkylineCommands.interaction_check
    on_error=SkylineCommands.on_error

    @app_commands.command(name='preview',description='List eligible Discord archives; deletion requires a separate typed confirmation.')
    async def preview(self,interaction:discord.Interaction,season:str|None=None,competition:str|None=None,
                      category:str|None=None,difficulty:str|None=None):
        scope={k:v for k,v in dict(season=season,competition=competition,category=category,level=difficulty).items() if v}
        await cleanup_ui.preview(self.client,interaction,scope)

    @app_commands.command(name='allow-recreate',description='Allow matching retired archives to be rebuilt on future scans; deleted discussions stay deleted.')
    async def allow_recreate(self,interaction:discord.Interaction,season:str|None=None,competition:str|None=None,
                            category:str|None=None,difficulty:str|None=None):
        scope={k:v for k,v in dict(season=season,competition=competition,category=category,level=difficulty).items() if v}
        await cleanup_ui.allow_recreation(self.client,interaction,scope)


class GuardedSurveyProbe:
    def __init__(self,client):
        self.client=client
        self.probe=SurveyProbe(client.settings)

    async def check(self,watch):
        if not watch.get('survey_url') and self.client.store.get('auth_invalid',False):
            raise SessionExpired('Waiting for the saved login to be refreshed and rechecked.')
        try:
            return await self.probe.check(watch)
        except SessionExpired as exc:
            await self.client.session_expired(str(exc),watch['channel_id'])
            raise


class SkylineBot(discord.Client):
    def __init__(self,settings):
        super().__init__(intents=discord.Intents(guilds=True,message_content=getattr(settings,'message_content',False)),
                         allowed_mentions=discord.AllowedMentions.none())
        self.settings=settings
        self.store=Store(settings.state_dir)
        self.jobs=Jobs(self.store)
        self.preferences=Preferences(self.store,settings)
        self.attachments=Attachments(self.store,preferences=self.preferences)
        self.archive=DiscordArchive(self,self.store,self.attachments,self.preferences)
        self.ai=OpenAIAssistant(self.store,settings)
        self.verifier=Verifier(self.store,self.attachments,ai=self.ai,
                               ai_enabled=lambda:self.preferences.effective()['ai_enabled'])
        self.tree=app_commands.CommandTree(self)
        self.tree.add_command(SkylineCommands(self),guild=discord.Object(id=settings.guild_id))
        self.tree.add_command(CleanupCommands(self),guild=discord.Object(id=settings.guild_id))
        self.archive_status='No scan run yet.'
        self.scan_task=None
        self.scan_phase='idle'
        self.scan_preview=False
        self.progress=None
        self.recovered=asyncio.Event()
        self.background=[]
        self.http_session=None
        self.surveys=SurveyManager(settings.state_dir/'survey-watches.json',GuardedSurveyProbe(self),self.send_survey_ping)
        self.scan_options={}
        self.pause_requested=False

    def busy(self):
        return self.scan_task is not None and not self.scan_task.done()

    async def setup_hook(self):
        self.http_session=aiohttp.ClientSession()
        await self.tree.sync(guild=discord.Object(id=self.settings.guild_id))
        self.background.append(asyncio.create_task(self.recover()))
        self.background.append(asyncio.create_task(self.survey_loop()))
        self.background.append(asyncio.create_task(self.schedule_loop()))

    async def recover(self):
        await self.wait_until_ready()
        try:
            await Cleanup(self).recover()
        except (ArchiveError,discord.HTTPException):
            LOG.warning('Cleanup reconciliation unavailable; retired archives remain held until checked.')
        for scan in self.store.interrupted_scans():
            if self.jobs.get(scan['id']):
                self.store.put('schedule_hold',True)
            if scan['message_id'] and scan['channel_id']:
                try:
                    channel=await self.archive.channel(scan['channel_id'])
                    message=await channel.fetch_message(scan['message_id']) if channel else None
                    if message:
                        await message.edit(content='**NCL TRACKER — interrupted by restart**\nSaved work and discussion were preserved. Use `/skyline resume` to continue from the checkpoint. Scheduled scans are held until resumed.')
                except (discord.HTTPException,ArchiveError):
                    pass
        self.recovered.set()

    def pause_sync(self):
        self.store.put('schedule_hold',True)
        if not self.busy():
            return 'Scheduled checks are paused. Use /skyline resume to continue.'
        if self.scan_phase.startswith('cleanup'):
            return 'Scheduled checks are paused. Use /skyline stop to stop remaining cleanup; completed deletions cannot be undone.'
        if self.scan_phase in ('checking login','indexing'):
            return 'Scheduled checks are paused. The current health/login/index check will finish normally.'
        self.pause_requested=True
        if self.scan_phase=='publishing':
            return 'Pause requested. The current publication will finish safely; remaining work stays saved.'
        if self.scan_phase not in ('pausing','stopping'):
            self.scan_phase='pausing'
            self.scan_task.cancel()
        return 'Pause requested. Complete collected challenges are saved; use /skyline resume to continue.'

    async def resume_interaction(self,interaction,retry=False):
        if self.busy():
            raise ArchiveError('A scan is already running; wait for it to pause or finish.')
        row=self.jobs.latest(failed=retry)
        if not row:
            if retry:
                raise ArchiveError('No saved failed scan items were found.')
            self.store.put('schedule_hold',False)
            await interaction.response.send_message('No paused scan remains. The schedule hold was released.',ephemeral=True)
            return
        options=json.loads(row['options'])
        options['resume_id']=row['id']
        await self.launch_interaction(interaction,**{k:v for k,v in options.items() if k!='owner'},preview=bool(row['preview']))
        self.store.put('schedule_hold',False)

    async def launch_interaction(self,interaction,**options):
        if self.busy():
            raise ArchiveError('A scan is already running. Use /skyline status or /skyline stop.')
        await interaction.response.defer(ephemeral=True)
        self.store.put('last_command_channel',interaction.channel_id)
        self.start_sync(channel=interaction.channel,owner=interaction.user.id,**options)
        await interaction.followup.send('Started. One progress message will update in the archive hub or this channel. '
            'Use `/skyline stop` to stop remaining work; completed posts are preserved.',ephemeral=True)

    def start_sync(self,event_url=None,all_events=False,preview=None,workflow=None,**options):
        if self.busy():
            raise ArchiveError('A scan is already running. Use /skyline status to check it or /skyline stop to cancel.')
        if workflow not in (None,'discord','github','both'):
            raise ArchiveError('Unknown archive workflow.')
        if workflow!='github' and self.store.get('auth_invalid',False):
            raise ArchiveError('Waiting for login. Refresh the session, then run /skyline session recheck.')
        prefs=self.preferences.effective()
        preview=prefs['default_preview'] if preview is None else preview
        if workflow in ('discord','both') and not prefs['archive_enabled'] and not preview:
            raise ArchiveError('Enable the Discord archive and choose its hub in /skyline settings first.')
        self.scan_options={**options,'preferences':prefs,'workflow':workflow or 'both'}
        self.pause_requested=False
        self.scan_phase='scanning'
        self.scan_preview=preview
        self.archive_status='Starting preview…' if preview else 'Starting scan…'
        self.progress=Progress(workflow=workflow or 'both')
        self.scan_task=asyncio.create_task(self.run_sync(event_url,all_events,preview))
        self.scan_task.add_done_callback(self.scan_finished)

    def stop_sync(self):
        if not self.busy():
            return 'No scan is running. Use `/skyline sync` or `/skyline sync-all` to start one.'
        if self.scan_phase.startswith('cleanup'):
            self.scan_task.cancel()
            return 'Cleanup stop requested. Completed deletions cannot be undone; run /skyline-cleanup preview before any retry.'
        if self.scan_phase=='publishing':
            return 'GitHub publication has already started and cannot be cancelled. Use `/skyline status` for its result.'
        if self.scan_phase in ('checking login','indexing'):
            return 'The login check or index migration is in progress; wait for its result.'
        if self.scan_phase=='stopping':
            return 'The scan is already stopping. Use `/skyline status` to check when cleanup finishes.'
        self.scan_phase='stopping'
        self.archive_status='Stopping remaining work. Saved questions and completed posts are preserved.'
        if self.progress:
            self.progress.update(state='stopping',detail=self.archive_status)
        self.scan_task.cancel()
        return 'Stop requested. Completed posts are preserved; pending work can be resumed. Use `/skyline status` for cleanup progress.'

    def scan_finished(self,task):
        if task is self.scan_task:
            if task.cancelled() and self.scan_phase=='pausing':
                self.archive_status='Paused. Scheduled checks are held; use /skyline resume.'
                if self.progress:
                    self.progress.update(state='paused',detail=self.archive_status)
            if task.cancelled() and self.scan_phase=='stopping':
                self.archive_status='Scan stopped. Saved questions and completed posts are preserved; use /skyline resume.'
                if self.progress:
                    self.progress.update(state='stopped',detail=self.archive_status)
            self.scan_phase='idle'

    async def session_expired(self,message,fallback=0):
        self.store.put('auth_invalid',True)
        prefs=self.preferences.effective()
        channel_id=prefs['notification_channel'] or prefs['archive_hub'] or fallback
        if not prefs['notify_login'] or not channel_id or self.store.get('auth_alert_sent',False):
            return
        # Persist before send: an ambiguous delivery must not repeat on restart.
        self.store.put('auth_alert_sent',True)
        try:
            channel=await self.archive.channel(channel_id)
            if channel:
                await channel.send('**Cyber Skyline login needs refreshing.**\nRun the existing local `python -m bots.skyline_archive login` workflow, replace the private session file on PebbleHost, then run `/skyline session recheck`. Scheduled archive attempts are paused until validation succeeds. Existing content is preserved.')
        except discord.HTTPException:
            LOG.warning('Login alert could not be delivered; see /skyline status.')

    async def run_sync(self,event_url,all_events,preview):
        options=dict(self.scan_options)
        workflow=options.get('workflow','both')
        prefs=options.get('preferences',self.preferences.effective())
        scope=options.get('scope',{})
        self.progress=self.progress or Progress()
        progress=self.progress
        live=None
        scan_id=None
        message=None
        pipeline=None
        source_channel=options.get('channel')
        watch_key='event-wait/'+(event_url or 'all')+('/preview' if preview else '/archive')
        if workflow!='both':
            watch_key+='/'+workflow
        try:
            destination=await self.archive.channel(prefs['archive_hub']) if prefs['archive_hub'] else source_channel
            resume=options.get('resume_id')
            if resume:
                previous=self.jobs.prepare_resume(resume)
                scan_id=resume
                progress.elapsed_before=json.loads(previous['progress']).get('elapsed',0)
            else:
                scan_id=self.jobs.create(dict(event_url=event_url,all_events=all_events,scope=scope,
                    owner=options.get('owner'),scheduled=options.get('scheduled',False),workflow=workflow,
                    archive_channel_id=options.get('archive_channel_id',0)),preview)
                previous=None
            waiting=self.store.get(watch_key)
            if destination:
                saved=previous or waiting
                if saved and saved.get('message_id') and saved.get('channel_id'):
                    try:
                        old_channel=await self.archive.channel(saved['channel_id'])
                        message=await old_channel.fetch_message(saved['message_id']) if old_channel else None
                    except discord.NotFound:
                        pass
                if message is None:
                    message=await destination.send(progress.render(preview))
                with self.store.db:
                    self.store.db.execute('UPDATE scans SET channel_id=?,message_id=? WHERE id=?',(message.channel.id,message.id,scan_id))
                def checkpoint():
                    with self.store.db:
                        self.store.db.execute('UPDATE scans SET state=?,progress=? WHERE id=?',
                            (progress.state,json.dumps(dict(processed=progress.processed,total=progress.total,
                            new=progress.new,skipped=progress.skipped,failed=progress.failed+progress.publication_failed,
                            elapsed=time.monotonic()-progress.started+progress.elapsed_before)),scan_id))
                live=ProgressMessage(message,progress,preview,checkpoint=checkpoint)
                live.start()
            if workflow=='github':
                await self.export_saved(scan_id,scope,options.get('archive_channel_id',0),preview)
                return
            scanner=Scanner(self.settings,lambda text:setattr(self,'archive_status',text),progress=progress)
            if options.get('catalog_only'):
                catalog=await scanner.discover()
                if scanner.discovery_errors:
                    progress.failed=len(scanner.discovery_errors)
                    progress.detail='Some pages were unavailable; the picker includes only discovered accessible content.'
                progress.update(state='discovery complete',total=len(catalog))
                self.store.put('catalog',catalog)
                if live:
                    await live.finish()
                    live=None
                if message:
                    view=Picker(self,options['owner'],catalog,warning=progress.detail if scanner.discovery_errors else '',workflow=workflow)
                    await message.edit(content=view.summary(),view=view)
                return
            if not preview:
                pipeline=DiscordPipeline(self,scan_id,prefs['archive_enabled'],progress)
            progress.collecting=True
            async def capture(c,context):
                target='discord' if prefs['archive_enabled'] else github_target(self.settings)
                if self.store.delivered(c,target):
                    progress.skipped+=1
                else:
                    progress.new+=1
                progress.attachment_total+=len(c.attachment_refs)
                if preview:
                    return
                self.store.upsert_challenge(c)
                for ref in c.attachment_refs:
                    progress.detail='Downloading '+ref.name[:120]
                    row=await self.attachments.fetch(c,ref,context)
                    if row['status'] in ('ready','uploaded','oversized-upload','upload-failed') and self.attachments.local_path(row):
                        progress.attachments+=1
                    else:
                        progress.attachment_failed+=1
                self.jobs.capture(scan_id,c)
                pipeline.offer(c.url)
            async def discovered(entries,complete):
                self.jobs.catalog(scan_id,entries,complete)
                if entries and waiting and not waiting.get('announced') and options.get('scheduled') and not preview:
                    waiting['announced']=True
                    self.store.put(watch_key,waiting) # At most once even after uncertain delivery.
                    try:
                        notify=await self.archive.channel(prefs['notification_channel']) if prefs['notification_channel'] else destination
                        if notify:
                            mentions=' '.join(f'<@{owner}>' for owner in sorted(self.settings.owners))
                            await notify.send(f'{mentions} The watched event is open. NCL TRACKER is scanning its questions.',
                                allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=x) for x in self.settings.owners],roles=False,everyone=False))
                    except (discord.HTTPException,ArchiveError):
                        LOG.warning('Event-open alert delivery failed; scanning continues.')
            async def failed(entry,error):
                self.jobs.state(scan_id,entry['url'],'failed',error)
            saved_items=self.jobs.items(scan_id)
            progress.new=sum(r['state']=='collected' for r in saved_items)
            progress.skipped=sum(r['state']=='published' for r in saved_items)
            skip_urls=[r['url'] for r in saved_items if r['state'] in ('collected','published')]
            if pipeline:
                for item in saved_items:
                    if item['state']=='collected':
                        pipeline.offer(item['url'])
            catalog=[json.loads(r['entry']) for r in saved_items if r['state']=='pending'] if resume and previous['discovery_complete'] else None
            result=await scanner.collect(event_url,all_events,scope=scope,on_challenge=capture,
                catalog=catalog,on_catalog=discovered,on_error=failed,skip_urls=skip_urls)
            progress.collecting=False
            if not preview:
                # Rediscovery may no longer include a previously accessible item.
                # Keep it retryable instead of reporting a completed checkpoint.
                for item in self.jobs.items(scan_id,'pending'):
                    error='Saved challenge was not collected; it may no longer be accessible in this session.'
                    self.jobs.state(scan_id,item['url'],'failed',error)
                    result.errors.append(error)
                    progress.failed+=1
                ready={r['url']:self.store.decode_challenge(r['payload']) for r in self.jobs.items(scan_id) if r['payload']}
                ready.update({c.url:c for c in result.challenges})
                result.challenges=list(ready.values())
                # Also support complete collectors which return a batch without callbacks.
                for c in result.challenges:
                    row=self.store.one('SELECT state FROM scan_items WHERE scan_id=? AND url=?',(scan_id,c.url))
                    if not row:
                        self.jobs.catalog(scan_id,[catalog_entry(c)],not bool(result.errors))
                        self.store.upsert_challenge(c)
                        self.jobs.capture(scan_id,c)
                    if not row or row['state']=='collected':
                        pipeline.offer(c.url)
            count=len(result.challenges)
            questions=sum(len(c.questions) for c in result.challenges)
            skipped=len(result.skipped_events)
            if not count:
                if result.waiting_events and not result.errors:
                    due=int(time.time()+prefs['frequency']*60)
                    detail='Event has not opened. '+(f'Next scheduled check <t:{due}:R>.' if prefs['enabled'] else 'Automatic checks are disabled.')
                    progress.update(state='waiting for event',detail=detail,competition=result.waiting_events[0]['name'])
                    self.archive_status=detail
                    self.store.put(watch_key,dict(channel_id=message.channel.id if message else 0,message_id=message.id if message else 0,announced=False))
                    return
                if resume and not result.errors and self.jobs.items(scan_id,'published'):
                    progress.update(state='completed',detail='All checkpoint items were already archived. No duplicate posts created.')
                    self.archive_status=progress.detail
                    return
                raise ArchiveError(f'No complete accessible questions found. {skipped} unavailable event(s). '+' '.join(result.errors[:2]))
            summary=f'{count} challenges / {questions} questions; {skipped} event(s) skipped; {len(result.errors)} page errors.'
            errors=list(result.errors)
            if preview:
                scopes={(c.category,level_and_title(c.title)[0]) for c in result.challenges}
                missing_categories=sum(self.store.mapping('category',cat.casefold()) is None for cat in {x[0] for x in scopes})
                missing_channels=sum(self.store.mapping('challenge-channel',c.key) is None for c in result.challenges)
                missing_threads=0
                for c in result.challenges:
                    current=self.store.rows('SELECT * FROM questions WHERE challenge_key=?',(c.key,))
                    mapped=self.store.mapping('challenge-channel',c.key)
                    missing_threads+=max(0,len(c.questions)-sum(bool(q['thread_id']) and q['channel_id']==mapped for q in current))
                enabled=prefs['archive_enabled']
                plan=f'Saved mappings indicate {missing_categories} new categories, {missing_channels} channels and {missing_threads} question threads; deleted Discord objects may also need repair.' if enabled else 'Discord archive is disabled; no categories, posts or threads would be created.'
                files=sum(len(c.attachment_refs) for c in result.challenges)
                self.archive_status=f'Preview complete: {summary} {plan} {files} file links discovered; sizes/downloadability not checked. No archive writes or uploads.'
            else:
                self.scan_phase='archiving'
                progress.update(state='archiving to Discord' if prefs['archive_enabled'] else 'preparing GitHub export',detail=summary)
                await pipeline.finish()
                errors.extend(pipeline.errors)
                progress.publication_failed=0
                self.archive_status='Complete: '+summary+f' {progress.discord_completed} Discord challenge archives completed this run.'
                if workflow=='both':
                    progress.update(state='publishing to GitHub',detail='Discord processing finished. '+summary)
                    try:
                        publication=await self.publish_github(result.challenges)
                        self.archive_status+=(f' {publication.changed} files changed. {publication.commit_url}' if publication.changed else ' GitHub is already up to date.')
                    except ArchiveError as exc:
                        error='GitHub export failed: '+str(exc)+' Discord archives were preserved.'
                        errors.append(error)
                        for item in self.jobs.items(scan_id,'published','collected'):
                            self.jobs.state(scan_id,item['url'],'failed',error)
                else:
                    self.archive_status+=' GitHub was not contacted. Use /skyline export-github when ready.'
                if self.pause_requested:
                    progress.update(state='paused',detail='Work saved. Use /skyline resume to release the schedule hold.')
                    self.archive_status=progress.detail
                    return
            if errors:
                self.archive_status+=' Pending errors: '+' '.join(errors[:2])+' Use /skyline retry-failed.'
            progress.update(state='completed with errors' if errors else 'completed',detail=self.archive_status,failed=len(errors))
            if waiting:
                self.store.put(watch_key,None)
            if prefs['notify_results'] and prefs['notification_channel'] and destination and destination.id!=prefs['notification_channel']:
                channel=await self.archive.channel(prefs['notification_channel'])
                if channel:
                    await channel.send('NCL TRACKER scan completed. '+(message.jump_url if message else self.archive_status[:1500]))
        except asyncio.CancelledError:
            state='paused' if self.pause_requested else ('stopped' if self.scan_phase=='stopping' else 'interrupted')
            if state!='stopped':
                self.store.put('schedule_hold',True)
            self.archive_status='Scan stopped. Saved questions and completed posts are preserved; use /skyline resume.' if state=='stopped' else 'Work saved. Use /skyline resume to continue; existing posts and threads are reused.'
            progress.update(state=state,detail=self.archive_status)
            raise
        except SessionExpired as exc:
            self.archive_status=str(exc)
            progress.update(state='waiting for login',detail=self.archive_status)
            await self.session_expired(str(exc),source_channel.id if source_channel else 0)
        except ArchiveError as exc:
            self.archive_status=str(exc)
            progress.update(state='failed',detail=self.archive_status)
            if scan_id:
                for item in self.jobs.items(scan_id,'collected'):
                    self.jobs.state(scan_id,item['url'],'failed',str(exc))
        except Exception as exc:
            self.archive_status=f'Scan failed ({type(exc).__name__}). Check host permissions, browser installation and configuration. Existing content is preserved.'
            progress.update(state='failed',detail=self.archive_status)
            LOG.error('Archive scan failed (%s)',type(exc).__name__)
        finally:
            progress.collecting=False
            if pipeline:
                await pipeline.close()
            if scan_id:
                with self.store.db:
                    self.store.db.execute('UPDATE scans SET state=?,progress=?,finished=? WHERE id=?',
                        (progress.state,json.dumps(dict(processed=progress.processed,new=progress.new,skipped=progress.skipped,failed=progress.failed,
                         elapsed=(progress.finished or time.monotonic())-progress.started+progress.elapsed_before)),now(),scan_id))
            if live:
                await live.finish()

    async def publish_github(self,challenges):
        self.scan_phase='publishing'  # Atomic ref update cannot be cancelled by /stop.
        try:
            publication=await GitHub(self.settings,self.http_session).publish(challenges)
            with self.store.db:
                for key,entry in getattr(publication,'manifest',{}).items():
                    for item in entry['files']:
                        self.store.db.execute('UPDATE questions SET github_path=? WHERE challenge_key=? AND number=?',
                                              (item['path'],key,item['number']))
            for c in challenges:
                self.store.mark_delivered(c,github_target(self.settings))
            self.store.put('last_success',now())
            return publication
        finally:
            self.scan_phase='archiving'

    async def export_saved(self,scan_id,scope,channel_id,preview):
        progress=self.progress
        candidates=await mapped_archives(self,scope,channel_id)
        self.jobs.catalog(scan_id,[catalog_entry(c) for c,_ in candidates],True)
        progress.update(state='checking Discord archives',total=len(candidates),processed=0)
        selected=[]
        errors=[]
        for c,questions in candidates:
            progress.update(competition=c.event,category=c.category,challenge=c.title)
            try:
                await validate_parents(self,c,questions)
                selected.append(c)
                if self.store.delivered(c,github_target(self.settings)):
                    progress.skipped+=1
                else:
                    progress.new+=1
                if not preview:
                    self.jobs.capture(scan_id,c)
            except (ArchiveError,discord.HTTPException) as exc:
                error=str(exc) if isinstance(exc,ArchiveError) else 'Discord archive could not be read; check permissions and retry.'
                errors.append(f'{c.title}: {error}')
                self.jobs.state(scan_id,c.url,'failed',error)
                progress.failed+=1
            progress.processed+=1
        if not selected:
            raise ArchiveError('No complete mapped Discord archives matched this scope. Run /skyline scan-discord first. '+' '.join(errors[:2]))
        count=sum(len(c.questions) for c in selected)
        if preview:
            self.archive_status=f'Preview complete: {len(selected)} challenges / {count} question files would be exported from saved Discord archives. '
            self.archive_status+='Existing GitHub files would be compared before writing. No source scan, Discord archive writes or GitHub uploads.'
        else:
            progress.update(state='publishing to GitHub',detail=f'Exporting {len(selected)} challenges / {count} questions. No Cyber Skyline visit.')
            publication=await self.publish_github(selected)
            for c in selected:
                self.jobs.state(scan_id,c.url,'published')
            self.archive_status=f'Complete: exported {len(selected)} Discord challenge archives / {count} questions. '
            self.archive_status+=(f'{publication.changed} files changed. {publication.commit_url}' if publication.changed else 'GitHub is already up to date.')
        if errors:
            self.archive_status+=' Pending errors: '+' '.join(errors[:2])+' Use /skyline failures.'
        progress.update(state='completed with errors' if errors else 'completed',detail=self.archive_status,failed=len(errors))

    async def verify_answer(self,interaction,question,answer):
        # The view callbacks recheck ownership; keep this shared boundary explicit too.
        if not await owner_check(self,interaction):
            return
        mapped=self.store.question(thread_id=interaction.channel_id)
        if not mapped or mapped['key']!=question['key']:
            raise ArchiveError('Verification must run in its original question thread.')
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        shown=json.dumps(answer,ensure_ascii=False)
        kwargs={}
        if len(shown)>1400:
            kwargs['file']=discord.File(io.BytesIO(answer.encode('utf-8')),filename='proposed-answer.txt')
            display='Exact answer attached as UTF-8; no whitespace was trimmed.'
        else:
            fence='`'*max(3,max((len(x) for x in re.findall(r'`+',shown)),default=0)+1)
            display=f'{fence}json\n{shown}\n{fence}'
        try:
            message=await interaction.channel.send(f'**Checking Q{question["number"]} — proposed answer**\n{display}',**kwargs)
        finally:
            if kwargs.get('file'):
                kwargs['file'].close()
        record=self.store.verification(question['key'],answer,interaction.user.id,dict(method='pending',
            outcome='Verification error',evidence='No completed result was recorded. The job may have been interrupted; retry verification.'))
        result=await self.verifier.check(question,answer)
        self.store.finish_verification(record,result)
        content=(f'**{result["outcome"]} — Q{question["number"]}**\n{display}\n'
                 f'**Method:** {discord.utils.escape_markdown(result["method"])}\n'
                 f'{discord.utils.escape_markdown(result["evidence"])}\nNo answer was submitted to Cyber Skyline.')
        if len(content)>1950:
            report=discord.File(io.BytesIO(content.encode('utf-8')),filename='verification-report.txt')
            try:
                await message.edit(content=f'**{result["outcome"]} — Q{question["number"]}**\n'
                    'The exact proposed answer, method and full evidence are in the attached report.\n'
                    'AI assessments are suggestions, not independent proof. No answer was submitted to Cyber Skyline.',
                    attachments=[*message.attachments,report])
            finally:
                report.close()
        else:
            await message.edit(content=content)
        try:
            await self.archive.update_verification(question)
        except discord.HTTPException:
            LOG.warning('Verification saved; parent post update failed.')
        await interaction.followup.send('Verification recorded in this thread.',ephemeral=True)

    async def send_survey_ping(self,watch,url):
        if watch['owner_id'] not in self.settings.owners or watch['guild_id']!=self.settings.guild_id:
            raise ArchiveError('Survey watch owner/server is no longer allowed.')
        channel=self.get_channel(watch['channel_id']) or await self.fetch_channel(watch['channel_id'])
        if not getattr(channel,'guild',None) or channel.guild.id!=self.settings.guild_id:
            raise ArchiveError('The survey channel is outside the configured server.')
        message=await channel.send(f"<@{watch['owner_id']}> The survey form is ready to fill out.\n<{url}>\nChallenge: <{watch['challenge_url']}>",
            allowed_mentions=discord.AllowedMentions(everyone=False,roles=False,users=[discord.Object(id=watch['owner_id'])],replied_user=False))
        return message.id

    async def survey_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self.surveys.tick()
            except Exception as exc:
                LOG.error('Survey state could not be updated (%s)',type(exc).__name__)
            await asyncio.sleep(60)

    async def schedule_loop(self):
        await self.wait_until_ready()
        await self.recovered.wait()
        while not self.is_closed():
            prefs=self.preferences.effective()
            last=self.store.get('last_scheduled',0)
            if prefs['enabled'] and not self.busy() and not self.store.get('auth_invalid',False) and not self.store.get('schedule_hold',False) and time.time()-last>=prefs['frequency']*60:
                try:
                    channel_id=prefs['archive_hub'] or prefs['notification_channel'] or self.store.get('last_command_channel',0)
                    channel=await self.archive.channel(channel_id) if channel_id else None
                    if channel is None:
                        self.archive_status='Scheduled scan waiting for an archive hub or notification destination in /skyline settings.'
                        await asyncio.sleep(15)
                        continue
                    self.start_sync(self.settings.event_url or None,all_events=not bool(self.settings.event_url),channel=channel,scheduled=True)
                    self.store.put('last_scheduled',time.time())
                except (ArchiveError,discord.HTTPException):
                    self.archive_status='Scheduled scan could not start. Check destination permissions and /skyline settings.'
            await asyncio.sleep(15)

    async def close(self):
        tasks=self.background+([self.scan_task] if self.scan_task else [])
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks,return_exceptions=True)
        if self.http_session:
            await self.http_session.close()
        self.store.close()
        await super().close()
