"""Outbound-only private web panel. No listening port, credentials or answers in status."""

import asyncio
from dataclasses import asdict
import json
import logging
import re
import time
from urllib.parse import urlsplit

import aiohttp
import discord

from .core import ArchiveError, SessionExpired, skyline_url
from .scanner import Scanner

LOG = logging.getLogger(__name__)
ACTIONS = {'scan-discord','scan-both','export-github','stop','pause','resume','retry-failed','settings','recheck'}
EDITABLE = {'enabled','frequency','fast_comp','default_preview','archive_hub','notification_channel','notify_login','notify_results'}


def configuration(path, owners):
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        p = urlsplit(data['url'])
        if (p.scheme != 'https' or not p.hostname or not p.hostname.endswith('.chatgpt.site')
                or p.username or p.password or p.port not in (None,443) or p.path not in ('','/') or p.query or p.fragment):
            raise ValueError()
        if int(data['owner_id']) not in owners:
            raise ValueError()
        if not all(isinstance(data[k],str) and len(data[k]) >= 32 for k in ('service_token','agent_token')):
            raise ValueError()
        return {**data,'url':data['url'].rstrip('/'),'owner_id':int(data['owner_id'])}
    except (KeyError,ValueError,TypeError,OSError):
        raise ArchiveError('Invalid private panel configuration. The Discord bot can still run.') from None


class PanelBridge:
    def __init__(self, client):
        self.client = client
        self.config = None
        try:
            self.config = configuration(client.settings.state_dir/'panel.json',client.settings.owners)
        except ArchiveError:
            LOG.warning('Web panel configuration is invalid; panel connection disabled.')
        self.url = self.config['url'] if self.config else ''
        self.last_error = None

    def snapshot(self):
        c = self.client
        p = c.preferences.effective()
        guild = c.get_guild(c.settings.guild_id)
        channels = []
        if guild:
            for ch in getattr(guild,'text_channels',[]):
                perms = ch.permissions_for(guild.me)
                if perms.view_channel and perms.send_messages:
                    channels.append({'id':str(ch.id),'name':ch.name})
        latest = c.store.one('SELECT id,state,preview,started,finished,channel_id,message_id FROM scans ORDER BY id DESC LIMIT 1')
        if latest:
            for key in ('channel_id','message_id'):
                latest[key]=str(latest[key]) if latest[key] else None
        failures = []
        scan, rows = c.jobs.failures(latest['id'] if latest else None)
        for row in rows[:30]:
            entry = json.loads(row['entry'])
            failures.append({'title':entry.get('title','Challenge'),'category':entry.get('category',''),
                             'error':row['error'],'url':row['url']})
        counts = {k:c.store.one(sql)['n'] for k,sql in {
            'challenges':'SELECT count(*) n FROM challenges',
            'questions':'SELECT count(*) n FROM questions WHERE thread_id IS NOT NULL',
            'channels':"SELECT count(*) n FROM mappings WHERE kind='challenge-channel'",
            'files':"SELECT count(*) n FROM attachments WHERE status IN ('ready','uploaded')"}.items()}
        catalog = c.store.get('catalog',[])
        events = {r.get('event_url'):r.get('event') for r in catalog if r.get('event_url')}
        for row in c.store.rows('SELECT DISTINCT event,source FROM challenges LIMIT 2000'):
            match = re.search(r'/module/([a-f0-9]{24})/',row['source'])
            if match:
                events['https://cyberskyline.com/world/'+match[1]]=row['event']
        if c.settings.event_url:
            events.setdefault(c.settings.event_url,'Configured competition')
        progress = asdict(c.progress) if c.progress else None
        if progress:
            progress['elapsed']=round((c.progress.finished or time.monotonic())-c.progress.started+c.progress.elapsed_before)
        recent = c.store.rows('SELECT id,state,preview,started,finished FROM scans ORDER BY id DESC LIMIT 8')
        return dict(version=1,busy=getattr(c,'local_busy',c.busy)(),phase=c.scan_phase,progress=progress,
            status=c.archive_status,preview=c.scan_preview,auth_invalid=c.store.get('auth_invalid',False),
            schedule_hold=c.store.get('schedule_hold',False),counts=counts,
            settings={k:(str(p[k]) if k.endswith('_channel') or k=='archive_hub' else p[k]) for k in EDITABLE},
            events=[dict(url=k,name=v) for k,v in sorted(events.items())],channels=channels,
            latest=latest,recent=recent,failures=failures,repository='https://github.com/'+c.settings.repository,
            discord='https://discord.com/channels/'+str(c.settings.guild_id),
            default_event=c.settings.event_url,owner_id=str(self.config['owner_id']) if self.config else '')

    async def execute(self, command):
        c = self.client
        ident = command.get('id','')
        if not isinstance(ident,str) or not re.fullmatch(r'[0-9a-f-]{36}',ident):
            raise ArchiveError('Invalid panel command identifier.')
        receipts = c.store.get('panel-receipts',{})
        if ident in receipts:
            return receipts[ident]
        result = {'id':ident,'ok':False,'message':'Interrupted before confirmation. Check status and resume if needed; this request will not run twice.'}
        receipts[ident]=result
        c.store.put('panel-receipts',dict(list(receipts.items())[-200:]))
        try:
            if not self.config or self.config['owner_id'] not in c.settings.owners:
                raise ArchiveError('The paired Discord owner is no longer authorized.')
            if str(command.get('owner_id')) != str(self.config['owner_id']):
                raise ArchiveError('This command belongs to another owner.')
            if not isinstance(command.get('expires'),(int,float)) or command['expires'] < time.time() or command['expires'] > time.time()+180:
                raise ArchiveError('This request expired. Send a fresh command from the panel.')
            action = command.get('action')
            if action not in ACTIONS:
                raise ArchiveError('Unsupported panel action.')
            payload = command.get('payload',{})
            if not isinstance(payload,dict):
                raise ArchiveError('Invalid panel options.')
            if action=='stop':
                message=c.stop_sync()
            elif action=='pause':
                message=c.pause_sync()
            elif action=='settings':
                if c.busy():
                    raise ArchiveError('Wait for the active operation before changing settings.')
                if not payload.keys() <= EDITABLE:
                    raise ArchiveError('This setting cannot be edited from the panel.')
                for k in ('archive_hub','notification_channel'):
                    if k in payload and isinstance(payload[k],str) and payload[k].isdecimal():
                        payload[k]=int(payload[k])
                await c.preferences.save(payload,c.get_guild(c.settings.guild_id))
                message='Settings saved. The next scan uses these defaults; existing archive mappings are preserved.'
            elif action=='recheck':
                if c.busy():
                    raise ArchiveError('Wait for the active operation before rechecking login.')
                async def check():
                    try:
                        await Scanner(c.settings).validate_session()
                        c.store.put('auth_invalid',False); c.store.put('auth_alert_sent',False)
                    except SessionExpired as exc:
                        await c.session_expired(str(exc))
                        raise
                    finally:
                        c.scan_phase='idle'
                c.scan_phase='checking login'
                c.scan_task=asyncio.create_task(check())
                await c.scan_task
                message='Login validated. Scans can run again.'
            else:
                if c.busy():
                    raise ArchiveError('An operation is already running. Wait, pause or stop it first.')
                options={}
                if action in ('resume','retry-failed'):
                    row=c.jobs.latest(failed=action=='retry-failed')
                    if not row:
                        if action=='retry-failed':
                            raise ArchiveError('No failed checkpoint was found.')
                        c.store.put('schedule_hold',False)
                        message='No paused scan remains; scheduled scans were released.'
                        result.update(ok=True,message=message)
                        receipts[ident]=result; c.store.put('panel-receipts',dict(list(receipts.items())[-200:]))
                        return result
                    options=json.loads(row['options'])
                    options.update(resume_id=row['id'],preview=bool(row['preview']))
                else:
                    if not payload.keys() <= {'event_url','all_events','preview','fast_comp'}:
                        raise ArchiveError('Unsupported scan option.')
                    for k in ('all_events','preview','fast_comp'):
                        if k in payload and type(payload[k]) is not bool:
                            raise ArchiveError('Scan switches must be true or false.')
                    options=dict(payload,workflow={'scan-discord':'discord','scan-both':'both','export-github':'github'}[action])
                    if options.get('all_events') and options.get('event_url'):
                        raise ArchiveError('Choose one event or all accessible events.')
                    if action!='export-github' and not options.get('all_events'):
                        options['event_url']=skyline_url(options.get('event_url') or c.settings.event_url)
                p=c.preferences.effective()
                channel=await c.archive.channel(p['archive_hub'] or p['notification_channel'] or c.store.get('last_command_channel',0))
                if channel is None:
                    raise ArchiveError('Select an accessible archive hub in settings first.')
                options.update(channel=channel,owner=self.config['owner_id'],panel_command=ident)
                c.start_sync(**options)
                if action=='resume':
                    c.store.put('schedule_hold',False)
                message='Started. Progress is shown here and in Discord.'
            result.update(ok=True,message=message)
        except ArchiveError as exc:
            result['message']=str(exc)[:1000]
        except (discord.HTTPException,aiohttp.ClientError,asyncio.TimeoutError):
            result['message']='The service could not be reached. Existing work was preserved; check status before retrying.'
        except Exception as exc:
            LOG.warning('Panel action failed (%s).',type(exc).__name__)
            result['message']='The action failed. Check bot health and configuration; existing archives were preserved.'
        receipts[ident]=result
        c.store.put('panel-receipts',dict(list(receipts.items())[-200:]))
        return result

    async def run(self):
        if not self.config:
            return
        c=self.client
        await c.wait_until_ready()
        await c.recovered.wait()
        headers={'OAI-Sites-Authorization':'Bearer '+self.config['service_token'],
                 'X-WS-Agent-Token':self.config['agent_token']}
        while not c.is_closed():
            try:
                body={'snapshot':self.snapshot(),'ack':c.store.get('panel-ack')}
                async with c.http_session.post(self.url+'/api/agent',json=body,headers=headers,
                    allow_redirects=False,timeout=aiohttp.ClientTimeout(total=20)) as response:
                    if response.status!=200:
                        raise ArchiveError('Panel connection unavailable')
                    data=await response.json()
                c.store.put('panel-ack',None)
                self.last_error=None
                if data.get('command'):
                    result=await self.execute(data['command'])
                    c.store.put('panel-ack',result)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self.last_error!=type(exc).__name__:
                    LOG.warning('Private web panel unavailable (%s); Discord commands still work.',type(exc).__name__)
                self.last_error=type(exc).__name__
            await asyncio.sleep(5 if self.last_error is None else 20)
