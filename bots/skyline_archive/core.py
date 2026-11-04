"""Validation and deterministic archive rendering (standard library only)."""

from dataclasses import dataclass
import hashlib
import html
import json
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit


ROOT = "challenges"
MANIFEST = "bots/skyline_archive/archive-manifest.json"
INDEX = "docs/skyline-questions.md"
ID = r"[a-f0-9]{24}"
WORLD = re.compile(rf"^/world/({ID})/?$")
MODULE = re.compile(rf"^/module/({ID})/({ID})/?$")
CHALLENGE = re.compile(rf"^/module/({ID})/({ID})/({ID})/?$")
FLAG_PATTERN = re.compile(r"\b(?:SKY-[A-Z]{4}-[0-9]{4}|(?:flag|ctf|cyber[ _-]*skyline)\\?\{[^}\r\n]+\})", re.I)
INSTANCE = re.compile(r"https?://[a-z0-9.-]+\.gateway\.cityinthe\.cloud[^\s<>)]*", re.I)
URL = re.compile(r"https?://[^\s<>]+", re.I)


class ArchiveError(Exception):
    """An actionable error safe to show in a private Discord reply."""


class SessionExpired(ArchiveError):
    """Authentication needs an explicit refresh; do not retry on a timer."""


@dataclass(frozen=True)
class AttachmentRef:
    name: str
    url: str


def skyline_url(value: str, kind: str = "event") -> str:
    """Limit crawler destinations to the observed Cyber Skyline page routes."""
    try:
        p = urlsplit(value.strip())
        safe = (p.scheme == "https" and p.hostname == "cyberskyline.com"
                and p.port in (None, 443) and not p.username and not p.password
                and not p.query and not p.fragment)
    except ValueError:
        safe = False
    patterns = {"event": WORLD, "module": MODULE, "challenge": CHALLENGE}
    if not safe or kind not in patterns or not patterns[kind].fullmatch(p.path):
        raise ArchiveError(f"Use a Cyber Skyline {kind} page URL without query parameters.")
    return urlunsplit(("https", "cyberskyline.com", p.path.rstrip("/"), "", ""))


def slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")[:64].strip("-") or "untitled"


def clean(value: str) -> str:
    """Redact common response/session material without evaluating page text."""
    value = INSTANCE.sub("[INSTANCE URL REMOVED]", value)
    value = FLAG_PATTERN.sub("[FLAG REMOVED]", value)
    # Preserve a link's purpose while removing query tokens and fragments.
    def redact_url(match):
        raw = match.group(0)
        trailing = ""
        while raw and raw[-1] in ").,;":
            trailing = raw[-1] + trailing
            raw = raw[:-1]
        try:
            p = urlsplit(raw)
            host = p.hostname or ""
            if p.port:
                host += f":{p.port}"
            return urlunsplit((p.scheme, host, p.path, "", "")) + trailing
        except ValueError:
            return "[URL REMOVED]" + trailing
    value = URL.sub(redact_url, value)
    value = re.sub(r"(?im)^\s*(?:final\s+)?(?:answer|flag)\s*[:=].+$", "[RESPONSE LINE REMOVED]", value)
    # Stored password hashes are disallowed by this repository's public policy.
    value = re.sub(r"\$[1256aby][^\s<]+", "[HASH REMOVED]", value)
    value = re.sub(r"\b(?:[a-f0-9]{32}|[a-f0-9]{40}|[a-f0-9]{64}|[a-f0-9]{128})\b", "[HASH-LIKE VALUE REMOVED]", value, flags=re.I)
    return value.replace("\r\n", "\n").strip()


def label(value: str) -> str:
    value = html.escape(clean(value).replace("\n", " "), quote=False)
    return re.sub(r"([\\`*_{}\[\]()|#!])", r"\\\1", value)


def git_blob_sha(content: str) -> str:
    raw = content.encode("utf-8")
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def event_location(event):
    season = re.search(r"\b(spring|summer|fall|autumn|winter)\s+((?:19|20)\d{2})\b", event, re.I)
    if not season:
        raise ArchiveError("The event title does not identify its season/year.")
    semester = season.group(1).lower().replace("autumn", "fall") + "-" + season.group(2)
    for expression, competition in (
        (r"\bgym(?:nasium)?\b", "gym"), (r"\bpractice\b", "practice-game"),
        (r"\bindividual\b", "individual"), (r"\bteam\b", "team-game"),
    ):
        if re.search(expression, event, re.I):
            return semester, competition
    raise ArchiveError("The event title does not identify gym, practice, individual, or team competition.")


def category_folder(category):
    aliases = {"web application exploitation": "web", "open source intelligence": "osint",
               "exploitation & enumeration": "enumeration-exploitation",
               "enumeration & exploitation": "enumeration-exploitation"}
    return aliases.get(category.casefold(), slug(category))


def level_and_title(title):
    match = re.search(r"\s*\((easy|medium|hard)\)\s*$", title, re.I)
    return (match.group(1).lower(), title[:match.start()].strip()) if match else ("unrated", title)


@dataclass(frozen=True)
class Challenge:
    url: str
    event: str
    category: str
    title: str
    prompt: str
    questions: tuple[str, ...]
    attachments: tuple[str, ...] = ()
    question_ids: tuple[str, ...] = ()
    attachment_refs: tuple[AttachmentRef, ...] = ()

    @property
    def ids(self):
        return CHALLENGE.fullmatch(urlsplit(skyline_url(self.url, "challenge")).path).groups()

    @property
    def key(self):
        return "/".join(self.ids)

    def path_for(self, number, collision=False):
        semester, competition = event_location(self.event)
        level, title = level_and_title(self.title)
        suffix = "-" + self.ids[2] if collision else ""
        name = slug(title)
        if re.match(r"^(?:answers?|flags?)(?:-|$)", name):
            name = "challenge-" + name
        return f"{ROOT}/{semester}/{competition}/{category_folder(self.category)}/{level}/{name}{suffix}-q{number}.md"

    def markdown(self, number):
        if not self.title.strip() or not self.category.strip() or not self.questions:
            raise ArchiveError("A challenge has missing title, category, or questions; nothing was uploaded.")
        if any(not q.strip() for q in self.questions):
            raise ArchiveError("A question was empty; the page layout needs checking.")
        if not 1 <= number <= len(self.questions):
            raise ArchiveError("Question number is out of range.")
        level, _ = level_and_title(self.title)
        lines = [f"# {label(self.title)} — Question {number}", "", f"**Event:** {label(self.event)}", "",
                 f"**Category:** {label(self.category)}", "", f"**Level:** {level}", "", f"**Source:** {self.url}", "",
                 "## Prompt", "", clean(self.prompt) or "See the question text below.", "",
                 f"## Question {number}", "", clean(self.questions[number - 1]), ""]
        if self.attachments:
            lines.extend(["## Referenced files", ""])
            lines.extend(f"- {label(name)}" for name in self.attachments)
            lines.extend(["", "Open the source challenge to download its original files.", ""])
        lines.extend(["---", "", "Imported question text. Response fields, submission history, and solution guides are excluded.", ""])
        return "\n".join(lines)


def archive_files(challenges, previous=None):
    """Merge a batch into the managed index; preserve unseen/closed challenges."""
    entries = dict(previous or {})
    files = {}
    seen = set()
    reserved = {f["path"] for e in entries.values() for f in e["files"]}
    for item in sorted(challenges, key=lambda c: c.key):
        if item.key in seen:
            raise ArchiveError("Duplicate challenge identity in one scan; nothing was uploaded.")
        seen.add(item.key)
        item.markdown(1)
        old_files = entries.get(item.key, {}).get("files", [])
        if len(old_files) > len(item.questions):
            raise ArchiveError("A source now contains fewer questions than its archive. Review that challenge before syncing.")
        own_paths = {f["path"] for f in old_files}
        collision = any(item.path_for(n) in reserved - own_paths for n in range(1, len(item.questions) + 1))
        question_files = []
        for number in range(1, len(item.questions) + 1):
            path = old_files[number - 1]["path"] if number <= len(old_files) else item.path_for(number, collision)
            if not valid_managed_path(path) or (path in reserved and path not in own_paths):
                raise ArchiveError("The archive contains conflicting question paths; no files were changed.")
            content = item.markdown(number)
            files[path] = content
            reserved.add(path)
            question_files.append({"number": number, "path": path, "sha": git_blob_sha(content)})
        semester, competition = event_location(item.event)
        entries[item.key] = {
            "files": question_files, "event": clean(item.event), "category": clean(item.category),
            "title": clean(item.title), "questions": len(item.questions),
            "season": semester, "competition": competition,
            "level": level_and_title(item.title)[0], "source": item.url,
        }
    if not seen:
        return {}
    files[MANIFEST] = json.dumps({"version": 2, "challenges": entries}, indent=2, sort_keys=True) + "\n"
    lines = ["# Cyber Skyline question archive", "", "One file per question, grouped by season, competition, category, and level.", "",
             "| Season | Competition | Category | Level | Challenge | Questions |", "| --- | --- | --- | --- | --- | --- |"]
    ordered = sorted(entries.values(), key=lambda e: (e["season"], e["competition"], e["category"], e["level"], e["title"], e["source"]))
    for entry in ordered:
        links = " · ".join(f"[Q{f['number']}](../{f['path']})" for f in entry["files"])
        lines.append(f"| {entry['season']} | {entry['competition']} | {label(entry['category'])} | {entry['level']} | {label(entry['title'])} | {links} |")
    files[INDEX] = "\n".join(lines) + "\n"
    return files


def valid_managed_path(path):
    return isinstance(path, str) and bool(re.fullmatch(
        r"challenges/(?:spring|summer|fall|winter)-(?:19|20)\d{2}/"
        r"(?:gym|practice-game|individual|team-game)/[a-z0-9-]+/"
        r"(?:easy|medium|hard|unrated)/[a-z0-9-]+-q[1-9]\d*\.md", path))


def parse_manifest(raw):
    try:
        data = json.loads(raw)
        entries = data["challenges"]
        if data["version"] != 2 or not isinstance(entries, dict):
            raise ValueError()
        paths = set()
        for key, e in entries.items():
            if not re.fullmatch(rf"{ID}/{ID}/{ID}", key) or not isinstance(e, dict):
                raise ValueError()
            if not all(isinstance(e[k], str) for k in ("event", "category", "title", "source", "season", "competition", "level")):
                raise ValueError()
            if not isinstance(e["questions"], int) or e["questions"] < 1 or len(e["files"]) != e["questions"]:
                raise ValueError()
            if event_location(e["event"]) != (e["season"], e["competition"]) or e["level"] not in ("easy", "medium", "hard", "unrated"):
                raise ValueError()
            for number, f in enumerate(e["files"], 1):
                if f["number"] != number or not valid_managed_path(f["path"]) or f["path"] in paths or not re.fullmatch(r"[a-f0-9]{40}", f["sha"]):
                    raise ValueError()
                paths.add(f["path"])
            if "/".join(CHALLENGE.fullmatch(urlsplit(skyline_url(e["source"], "challenge")).path).groups()) != key:
                raise ValueError()
        return entries
    except (ValueError, KeyError, TypeError, ArchiveError) as exc:
        raise ArchiveError("The existing archive manifest is invalid; no files were changed.") from exc
