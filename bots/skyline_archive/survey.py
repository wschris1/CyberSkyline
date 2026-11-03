"""Watch for a usable survey, rather than treating HTTP 200 as readiness."""

import asyncio
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
from urllib.parse import urlsplit

from .core import ArchiveError, skyline_url


def now():
    return datetime.now(timezone.utc).isoformat()


def form_url(value):
    try:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.port not in (None, 443) or len(value) > 1500
                or any(c.isspace() for c in value)):
            raise ValueError()
        host = url.hostname.lower().rstrip(".")
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address and not address.is_global:
            raise ValueError()
    except ValueError as exc:
        raise ArchiveError("Use an HTTPS survey URL on a public website, without embedded credentials.") from exc
    return value


async def public_host(value):
    url = urlsplit(form_url(value))
    try:
        addresses = await asyncio.get_running_loop().getaddrinfo(url.hostname, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ArchiveError("The survey hostname is not resolving yet.") from exc
    if not addresses or any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ArchiveError("The survey URL does not resolve to a public address.")


BLOCKED = re.compile(
    r"not accepting responses|no longer accepting|not yet (?:open|available)|"
    r"survey (?:is |has been )?(?:currently )?(?:closed|unavailable)|"
    r"form (?:is |has been )?(?:currently )?closed|coming soon|access denied|"
    r"page not found|service unavailable|this site can.t be reached|"
    r"sign in to|log in to|you need permission|request access|"
    r"(?:^|\n)\s*(?:sign in|log in)\s*(?:\n|$)", re.I)


def is_ready(snapshot, required_text=""):
    """Only visible usable form controls qualify; headings alone never qualify."""
    body = snapshot.get("text", "")
    if BLOCKED.search(body) or snapshot.get("password", False):
        return False
    if required_text and required_text.casefold() not in body.casefold():
        return False
    return bool(snapshot.get("fields", 0) and snapshot.get("actions", 0))


SURVEY_LINKS = """() => Array.from(document.querySelectorAll(
  '.ui.basic.segment.body:not(.fat) a[href], .ui.basic.segment.body:not(.fat) iframe[src]'
)).map(e => ({url: e.href || e.src, label: e.textContent || e.title || ''}))
 .filter(e => !new URL(e.url).pathname.startsWith('/artifact/'))
 .filter(e => /survey|forms\\.gle|docs\\.google\\.com\\/forms|forms\\.office\\.com|qualtrics|surveymonkey|typeform/i.test(e.url + ' ' + e.label))"""

FORM_STATE = """() => {
  const visible = e => {
    const s = getComputedStyle(e);
    return !!e.getClientRects().length && s.visibility !== 'hidden' && s.display !== 'none';
  };
  const editable = e => visible(e) && !e.disabled && !e.readOnly && e.getAttribute('aria-disabled') !== 'true';
  const fields = Array.from(document.querySelectorAll(
    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="search"]),'
    + 'textarea, select, [role="radio"], [role="checkbox"], [role="textbox"], [role="combobox"]'
  )).filter(editable).length;
  const actions = Array.from(document.querySelectorAll('button, input[type="submit"], [role="button"]'))
    .filter(visible).filter(e => [e.innerText, e.value, e.getAttribute('aria-label'), e.title]
      .some(t => /^(submit|next|continue|finish|send|complete|start)(\\b|$)/i.test((t || '').trim()))
      || /^(nextbutton|submitbutton|next|submit|continue)$/i.test(e.id || '')).length;
  return {text: document.body.innerText.slice(0, 150000), fields, actions,
    password: Array.from(document.querySelectorAll('input[type="password"]')).some(visible)};
}"""


class SurveyProbe:
    def __init__(self, settings):
        self.settings = settings

    async def check(self, watch):
        from playwright.async_api import async_playwright
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=self.settings.headless)
            try:
                target = watch.get("survey_url", "")
                if not target:
                    if not self.settings.auth_file.is_file():
                        raise ArchiveError("Run the local login command to check this challenge.")
                    source = await browser.new_context(storage_state=str(self.settings.auth_file), accept_downloads=False)
                    page = await source.new_page()
                    response = await page.goto(watch["challenge_url"], wait_until="domcontentloaded", timeout=30000)
                    if not response or response.status >= 400:
                        return False, "The challenge page is not available yet.", ""
                    if "/module/" not in urlsplit(page.url).path:
                        raise ArchiveError("Cyber Skyline needs login again, or this challenge is unavailable.")
                    # Allow asynchronous prompt rendering without requiring an answer table.
                    for _ in range(12):
                        links = await page.evaluate(SURVEY_LINKS)
                        if links:
                            break
                        await asyncio.sleep(0.5)
                    targets = sorted({e["url"] for e in links})
                    if not targets:
                        return False, "Challenge open; waiting for its survey link.", ""
                    if len(targets) > 1:
                        return False, "Multiple survey links found. Set survey_url explicitly.", ""
                    target = targets[0]
                    await source.close()
                await public_host(target)
                # External surveys do not receive the Cyber Skyline authenticated context.
                context = await browser.new_context(accept_downloads=False)
                async def restrict(route):
                    try:
                        # Check navigations, redirects, frames, and resource destinations.
                        await public_host(route.request.url)
                    except ArchiveError:
                        await route.abort()
                    else:
                        await route.continue_()
                await context.route("**/*", restrict)
                page = await context.new_page()
                response = await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                if not response or not 200 <= response.status < 300:
                    return False, "Survey website has not loaded successfully yet.", ""
                for _ in range(12):
                    for frame in page.frames:
                        try:
                            state = await frame.evaluate(FORM_STATE)
                        except Exception:
                            continue
                        if is_ready(state, watch.get("ready_text", "")):
                            return True, "A visible survey form is ready.", page.url
                    await asyncio.sleep(0.5)
                return False, "Website reachable; still waiting for a usable survey form.", ""
            finally:
                await browser.close()


def write_private_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class SurveyManager:
    """Persist watchers and notification state outside the Git repository."""
    def __init__(self, path, probe, send):
        self.path = Path(path)
        self.probe = probe
        self.send = send
        self.watches = {}
        if self.path.is_file():
            try:
                self.watches = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(self.watches, dict):
                    raise ValueError()
                for item in self.watches.values():
                    if not isinstance(item, dict) or item["delivery"] not in ("watching", "sending", "sent", "uncertain"):
                        raise ValueError()
                    skyline_url(item["challenge_url"], "challenge")
                    if item.get("survey_url"):
                        form_url(item["survey_url"])
                    for name in ("owner_id", "channel_id", "guild_id"):
                        if not isinstance(item[name], int) or item[name] <= 0:
                            raise ValueError()
                    if item["delivery"] == "sending":
                        item["delivery"] = "uncertain"
                    item["streak"] = 0  # A restart cannot count an old readiness observation.
            except (ValueError, KeyError, TypeError) as exc:
                raise ArchiveError("The local survey watch file is invalid. Preserve it and fix it before starting.") from exc

    def save(self):
        write_private_json(self.path, self.watches)

    def add(self, challenge_url, survey_url, ready_text, owner_id, channel_id, guild_id):
        challenge_url = skyline_url(challenge_url, "challenge")
        if survey_url:
            form_url(survey_url)
        if len(ready_text) > 200:
            raise ArchiveError("ready_text must be 200 characters or fewer.")
        key = hashlib.sha256(f"{owner_id}:{channel_id}:{challenge_url}".encode()).hexdigest()[:12]
        if key in self.watches:
            raise ArchiveError(f"Watch {key} already exists. Use /skyline unwatch-survey before rearming it.")
        if len(self.watches) >= 10:
            raise ArchiveError("Remove an old watch first; this bot supports up to 10 watches.")
        self.watches[key] = {"challenge_url": challenge_url, "survey_url": survey_url, "ready_text": ready_text,
                             "owner_id": owner_id, "channel_id": channel_id, "guild_id": guild_id,
                             "delivery": "watching", "streak": 0, "status": "Waiting for first check.",
                             "created": now(), "checked": None}
        self.save()
        return key

    async def tick(self):
        for key, watch in list(self.watches.items()):
            if watch["delivery"] != "watching":
                continue
            try:
                ready, status, url = await self.probe.check(watch)
            except ArchiveError as exc:
                ready, status, url = False, str(exc), ""
            except Exception:
                ready, status, url = False, "Browser/network check failed; it will retry. Check the host browser installation.", ""
            if self.watches.get(key) is not watch:
                continue
            watch.update(checked=now(), status=status, streak=watch["streak"] + 1 if ready else 0)
            if watch["streak"] < 2:
                self.save()
                continue
            # Persist before sending. A crash or ambiguous delivery must not cause repeat pings.
            watch["delivery"] = "sending"
            self.save()
            try:
                message_id = await self.send(watch, url)
            except Exception:
                watch["delivery"] = "uncertain"
                watch["status"] = "Ping delivery uncertain. Check the channel before removing/rearming this watch."
            else:
                watch.update(delivery="sent", message_id=message_id, status="Survey ready; Discord ping sent.")
            self.save()
