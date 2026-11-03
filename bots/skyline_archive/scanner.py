"""Walk event/module/challenge links using a separately authenticated browser."""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit

from .core import ArchiveError, Challenge, WORLD, MODULE, CHALLENGE, skyline_url, event_location


EXTRACTOR = Path(__file__).with_name("dom_extract.js").read_text(encoding="utf-8")


@dataclass
class ScanResult:
    challenges: list = field(default_factory=list)
    skipped_events: list = field(default_factory=list)
    errors: list = field(default_factory=list)


def links_for(snapshot, pattern, prefix=""):
    found = {}
    for link in snapshot.get("links", []):
        href = link.get("href", "")
        if pattern.fullmatch(href) and (not prefix or href.startswith(prefix)):
            found.setdefault(urljoin("https://cyberskyline.com", href), link.get("title", ""))
    return found


class Scanner:
    def __init__(self, settings, report=lambda text: None):
        self.settings = settings
        self.report = report
        self.page = None
        self.visited = 0
        self.last_visit = 0.0

    async def visit(self, url, kind, timeout=40):
        from playwright.async_api import TimeoutError as PlaywrightTimeout
        wait = self.settings.delay - (time.monotonic() - self.last_visit)
        if wait > 0:
            await asyncio.sleep(wait)
        self.last_visit = time.monotonic()
        self.visited += 1
        try:
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
            if response and response.status >= 400:
                raise ArchiveError(f"Cyber Skyline returned HTTP {response.status}.")
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                parsed = urlsplit(self.page.url)
                if parsed.hostname != "cyberskyline.com" or any(x in parsed.path.lower() for x in ("login", "signin", "sign-in")):
                    raise ArchiveError("Cyber Skyline login expired. Run the local login command again.")
                snapshot = await self.page.evaluate(EXTRACTOR)
                if kind == "challenge" and snapshot.get("challenge"):
                    return snapshot
                if kind == "module" and links_for(snapshot, CHALLENGE):
                    return snapshot
                if kind == "event" and snapshot.get("event"):
                    # React can render a heading before its module cards.
                    if links_for(snapshot, MODULE):
                        return snapshot
                    import re
                    unavailable = re.compile(r"This challenge has ended|Starting in:|Opening in:", re.I)
                    if await self.page.get_by_role("heading", name=unavailable).count():
                        return snapshot
                if kind == "events" and links_for(snapshot, WORLD):
                    return snapshot
                if await self.page.locator('input[type="password"]').count():
                    raise ArchiveError("Cyber Skyline needs sign-in. Run the local login command again.")
                await asyncio.sleep(0.5)
        except PlaywrightTimeout as exc:
            raise ArchiveError("Cyber Skyline timed out; rerun the scan after checking your connection.") from exc
        raise ArchiveError(f"The {kind} page did not expose the expected content. Check access or page layout.")

    async def collect(self, event_url=None, all_events=False):
        from playwright.async_api import async_playwright
        if not self.settings.auth_file.is_file():
            raise ArchiveError("No Cyber Skyline session saved. Run: python -m bots.skyline_archive login")
        if not all_events:
            event_url = skyline_url(event_url or self.settings.event_url)
        result = ScanResult()
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.settings.headless)
            try:
                context = await browser.new_context(storage_state=str(self.settings.auth_file), accept_downloads=False)
                self.page = await context.new_page()
                if all_events:
                    dashboard = await self.visit("https://cyberskyline.com/competition", "events")
                    events = links_for(dashboard, WORLD)
                else:
                    events = {event_url: ""}
                if not events:
                    raise ArchiveError("No accessible event links were found.")
                for index, (url, name) in enumerate(events.items(), 1):
                    self.report(f"Reading event {index}/{len(events)}; collected {len(result.challenges)} challenges.")
                    try:
                        event = await self.visit(url, "event")
                    except ArchiveError as exc:
                        # Authentication failures must never be reported as successful empty scans.
                        if "sign-in" in str(exc) or "login" in str(exc):
                            raise
                        result.errors.append(f"Event {urlsplit(url).path.rsplit('/', 1)[-1]}: {exc}")
                        continue
                    name = event.get("event") or name or "Cyber Skyline event"
                    try:
                        event_location(name)
                    except ArchiveError:
                        if all_events:
                            result.skipped_events.append(name + " (season or competition type missing)")
                            continue
                        raise ArchiveError("This event needs a season/year and competition type in its title to fit your folders.")
                    world_id = WORLD.fullmatch(urlsplit(url).path).group(1)
                    modules = links_for(event, MODULE, f"/module/{world_id}/")
                    if not modules:
                        result.skipped_events.append(name)
                        continue
                    for module_url in modules:
                        module_path = urlsplit(module_url).path
                        try:
                            module = await self.visit(module_url, "module")
                        except ArchiveError as exc:
                            result.errors.append(f"Module {module_path.rsplit('/', 1)[-1]}: {exc}")
                            continue
                        challenge_links = links_for(module, CHALLENGE, module_path + "/")
                        for challenge_url in challenge_links:
                            if len(result.challenges) >= self.settings.max_challenges:
                                raise ArchiveError("MAX_CHALLENGES reached. Increase it or scan a single event; nothing was uploaded.")
                            self.report(f"Collected {len(result.challenges)} challenges; scanning the next question page.")
                            try:
                                # The module route redirects to its first challenge. Reuse that page once.
                                if self.page.url.rstrip("/") == challenge_url and module.get("challenge"):
                                    page = module
                                else:
                                    page = await self.visit(challenge_url, "challenge")
                                if self.page.url.rstrip("/") != challenge_url:
                                    raise ArchiveError("A challenge redirected to another page.")
                                item = page["challenge"]
                                qids = item.get("question_ids", [])
                                if len(qids) != len(item["questions"]) or len(set(qids)) != len(qids):
                                    raise ArchiveError("The question table contains duplicate or incomplete rows.")
                                challenge = Challenge(challenge_url, name, item["category"], item["title"],
                                                      item["prompt"], tuple(item["questions"]), tuple(item["attachments"]))
                                challenge.markdown(1)  # Validate before adding anything to the batch.
                                result.challenges.append(challenge)
                            except ArchiveError as exc:
                                result.errors.append(f"Challenge {urlsplit(challenge_url).path.rsplit('/', 1)[-1]}: {exc}")
                return result
            finally:
                await browser.close()


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
