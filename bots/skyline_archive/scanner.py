"""Read authorized rendered pages, discovering scope before counting scan work."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit

from .core import (ArchiveError, AttachmentRef, Challenge, SessionExpired, WORLD, MODULE,
                   CHALLENGE, skyline_url, event_location, level_and_title)

EXTRACTOR = Path(__file__).with_name('dom_extract.js').read_text(encoding='utf-8')


@dataclass
class ScanResult:
    challenges: list = field(default_factory=list)
    skipped_events: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def links_for(snapshot, pattern, prefix=''):
    found = {}
    for link in snapshot.get('links', []):
        href = link.get('href', '')
        if pattern.fullmatch(href) and (not prefix or href.startswith(prefix)):
            found.setdefault(urljoin('https://cyberskyline.com', href), link.get('title', ''))
    return found


def matches(item, scope):
    return all(not scope.get(k) or item.get(k, '').casefold() == scope[k].casefold()
               for k in ('season','competition','event_url','category','level'))


def validate_saved_session(settings):
    if not settings.auth_file.is_file():
        raise SessionExpired('No Cyber Skyline login saved. Refresh the local login, then run /skyline session recheck.')
    try:
        state = json.loads(settings.auth_file.read_text(encoding='utf-8'))
        if not isinstance(state,dict) or not isinstance(state.get('cookies'),list) or not isinstance(state.get('origins'),list):
            raise ValueError()
    except (ValueError, UnicodeError):
        raise SessionExpired('The saved login is invalid. Refresh it, then run /skyline session recheck.') from None


class Scanner:
    def __init__(self, settings, report=lambda text: None, progress=None):
        self.settings, self.report, self.progress = settings, report, progress
        self.page = None
        self.visited = 0
        self.last_visit = 0.0
        self.discovery_errors = []
        self.skipped_events = []

    def update(self, **values):
        if self.progress:
            self.progress.update(**values)

    @asynccontextmanager
    async def opened(self):
        from playwright.async_api import async_playwright, Error
        validate_saved_session(self.settings)
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.settings.headless)
            try:
                try:
                    context = await browser.new_context(storage_state=str(self.settings.auth_file), accept_downloads=False)
                except Error as exc:
                    if 'storageState' in str(exc) or 'storage state' in str(exc):
                        raise SessionExpired('The saved login is invalid; refresh it and recheck the session.') from None
                    raise
                self.page = await context.new_page()
                yield context
            finally:
                await browser.close()

    async def visit(self, url, kind, timeout=40):
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        wait = self.settings.delay - (time.monotonic() - self.last_visit)
        if wait > 0:
            await asyncio.sleep(wait)
        self.last_visit = time.monotonic()
        self.visited += 1
        try:
            response = await self.page.goto(url, wait_until='domcontentloaded', timeout=45000)
            if response and response.status == 401:
                raise SessionExpired('Cyber Skyline login expired. Refresh it, then run /skyline session recheck.')
            if response and response.status >= 400:
                raise ArchiveError(f'Cyber Skyline returned HTTP {response.status}; access or network failure.')
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                parsed = urlsplit(self.page.url)
                if any(x in parsed.path.lower() for x in ('login','signin','sign-in')):
                    raise SessionExpired('Cyber Skyline login expired. Refresh it, then run /skyline session recheck.')
                if parsed.hostname != 'cyberskyline.com':
                    raise ArchiveError('Cyber Skyline redirected to an unexpected website; check access or service status.')
                snapshot = await self.page.evaluate(EXTRACTOR)
                if kind == 'challenge' and snapshot.get('challenge'):
                    return snapshot
                if kind == 'module' and links_for(snapshot, CHALLENGE):
                    return snapshot
                if kind == 'event' and snapshot.get('event'):
                    if links_for(snapshot, MODULE):
                        return snapshot
                    import re
                    unavailable = re.compile(r'This challenge has ended|Starting in:|Opening in:', re.I)
                    if await self.page.get_by_role('heading', name=unavailable).count():
                        return snapshot
                if kind == 'events' and links_for(snapshot, WORLD):
                    return snapshot
                if await self.page.locator('input[type="password"]').count():
                    raise SessionExpired('Cyber Skyline needs sign-in. Refresh the login, then recheck the session.')
                await asyncio.sleep(0.5)
        except PlaywrightTimeout as exc:
            raise ArchiveError('Cyber Skyline timed out; check the connection and retry.') from exc
        raise ArchiveError(f'The {kind} page did not expose the expected content. Check access or page layout.')

    async def validate_session(self):
        async with self.opened():
            await self.visit('https://cyberskyline.com/competition', 'events')
        return True

    async def _discover(self, event_url=None, all_events=False, scope=None):
        scope = scope or {}
        self.discovery_errors, self.skipped_events = [], []
        self.update(state='discovering challenges', total=None, processed=0)
        if all_events:
            dashboard = await self.visit('https://cyberskyline.com/competition', 'events')
            events = links_for(dashboard, WORLD)
        else:
            events = {skyline_url(event_url or self.settings.event_url): ''}
        entries = {}
        for index, (url, name) in enumerate(events.items(), 1):
            if scope.get('event_url') and scope['event_url'] != url:
                continue
            self.report(f'Discovering event {index}/{len(events)}; total challenge count is not known yet.')
            self.update(competition=name, category='', challenge='')
            try:
                event = await self.visit(url, 'event')
                name = event.get('event') or name
                try:
                    season, competition = event_location(name)
                except ArchiveError:
                    self.skipped_events.append(name or 'Event without season/type')
                    continue
                base = dict(event=name,event_url=url,season=season,competition=competition)
                if not matches(base, {k:v for k,v in scope.items() if k not in ('category','level')}):
                    continue
                world = WORLD.fullmatch(urlsplit(url).path).group(1)
                modules = links_for(event,MODULE,f'/module/{world}/')
                if not modules:
                    self.skipped_events.append(name)
                for module_url, module_title in modules.items():
                    self.update(competition=name,category=module_title)
                    try:
                        module = await self.visit(module_url, 'module')
                        category = module.get('category') or (module.get('challenge') or {}).get('category') or module_title
                        if scope.get('category') and category.casefold() != scope['category'].casefold():
                            continue
                        for challenge_url, title in links_for(module, CHALLENGE, urlsplit(module_url).path + '/').items():
                            row = dict(base,url=challenge_url,title=title,category=category,level=level_and_title(title)[0])
                            if matches(row, scope):
                                entries[challenge_url] = row
                            if len(entries) > self.settings.max_challenges:
                                raise ArchiveError('MAX_CHALLENGES reached. Select a smaller scope before scanning.')
                    except SessionExpired:
                        raise
                    except ArchiveError as exc:
                        self.discovery_errors.append(f'Module {module_title or "unavailable"}: {exc}')
            except SessionExpired:
                raise
            except ArchiveError as exc:
                self.discovery_errors.append(f'Event {name or index}: {exc}')
        self.update(failed=len(self.discovery_errors), skipped=0,
                    detail=f'{len(self.skipped_events)} unavailable event(s) skipped during discovery.')
        if len(entries) > self.settings.max_challenges:
            raise ArchiveError('MAX_CHALLENGES reached. Select a smaller scope; nothing was published.')
        return list(entries.values())

    async def discover(self, scope=None):
        async with self.opened():
            entries = await self._discover(all_events=True, scope=scope)
        return entries

    async def collect(self, event_url=None, all_events=False, *, scope=None, catalog=None, on_challenge=None):
        scope = scope or {}
        result = ScanResult()
        async with self.opened() as context:
            entries = await self._discover(event_url, all_events, scope) if catalog is None else [e for e in catalog if matches(e,scope)]
            result.errors.extend(self.discovery_errors)
            result.skipped_events.extend(self.skipped_events)
            self.update(state='scanning',total=None if self.discovery_errors else len(entries),processed=0,scan_started=time.monotonic())
            for number, entry in enumerate(entries,1):
                url = entry['url']
                self.update(competition=entry['event'],category=entry['category'],challenge=entry['title'])
                self.report(f'Scanning {number}/{len(entries)}; collected {len(result.challenges)} challenges.')
                try:
                    page = await self.visit(url,'challenge')
                    if self.page.url.rstrip('/') != url:
                        raise ArchiveError('A challenge redirected to another page.')
                    item = page['challenge']
                    qids = item.get('question_ids', [])
                    if len(qids) != len(item['questions']) or len(set(qids)) != len(qids):
                        raise ArchiveError('The question table contains duplicate or incomplete rows.')
                    actual = dict(entry,category=item['category'],level=level_and_title(item['title'])[0])
                    if not matches(actual,scope):
                        if self.progress:
                            self.progress.skipped += 1
                        continue
                    refs = tuple(AttachmentRef(a['name'],a['url']) for a in item.get('attachment_refs',[]))
                    c = Challenge(url,entry['event'],item['category'],item['title'],item['prompt'],
                                  tuple(item['questions']),tuple(item['attachments']),tuple(qids),refs)
                    c.markdown(1)
                    result.challenges.append(c)
                    if on_challenge:
                        await on_challenge(c,context)
                except SessionExpired:
                    raise
                except ArchiveError as exc:
                    result.errors.append(f'Challenge {entry["title"] or number}: {exc}')
                finally:
                    self.update(processed=number,failed=len(result.errors))
        return result

async def login(settings):
    from playwright.async_api import async_playwright
    import os
    settings.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://cyberskyline.com/competition")
            print("Sign in in the opened browser, then open your Competition dashboard.")
            await asyncio.to_thread(input, "Once event cards are visible, press Enter here: ")
            snapshot = await page.evaluate(EXTRACTOR)
            if urlsplit(page.url).hostname != "cyberskyline.com" or not links_for(snapshot, WORLD):
                raise ArchiveError("No event cards found. Login state was not saved; try again from the dashboard.")
            temporary = settings.auth_file.with_suffix(".tmp")
            try:
                # Pre-create with restrictive POSIX permissions before browser state is written.
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                os.close(fd)
                os.chmod(temporary, 0o600)
                await context.storage_state(path=str(temporary), indexed_db=True)
                os.replace(temporary, settings.auth_file)
            finally:
                temporary.unlink(missing_ok=True)
            print("Cyber Skyline session saved privately. You can now start the bot.")
        finally:
            await browser.close()
