"""Publish a batch through GitHub Git objects with non-forced ref updates."""

import asyncio
import base64
from dataclasses import dataclass, field
from urllib.parse import quote

from .core import ArchiveError, MANIFEST, INDEX, archive_files, git_blob_sha, parse_manifest


class ApiError(ArchiveError):
    def __init__(self, status):
        self.status = status
        messages = {
            401: "GitHub rejected the token. Check GITHUB_TOKEN.",
            403: "GitHub denied access or rate-limited this request. Check Contents write permission and branch rules.",
            404: "GitHub repository, branch, or file was not found. Check the repository and token access.",
            409: "GitHub changed during upload. Retry the sync.",
            422: "GitHub rejected the update. Check branch protection or retry after concurrent changes.",
            429: "GitHub rate-limited the bot. Wait before retrying.",
        }
        super().__init__(messages.get(status, f"GitHub returned HTTP {status}. No forced update was attempted."))


@dataclass(frozen=True)
class PublishResult:
    changed: int
    commit_url: str | None
    manifest: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ArchiveProof:
    head: str
    manifest: dict
    blobs: dict

    def check(self, challenge):
        """Require every current rendered prompt at this exact immutable commit."""
        entry = self.manifest.get(challenge.key)
        if not entry or len(entry['files']) != len(challenge.questions):
            return 'GitHub does not contain every question in this challenge.'
        for item in entry['files']:
            expected = git_blob_sha(challenge.markdown(item['number']))
            if item['sha'] != expected or self.blobs.get(item['path']) != expected:
                return 'A GitHub question is missing, changed, or older than the saved source prompt.'
        return None


class GitHub:
    def __init__(self, settings, session):
        self.settings = settings
        self.session = session
        self.base = "https://api.github.com/repos/" + settings.repository

    async def request(self, method, path, payload=None):
        import aiohttp
        if not getattr(self.settings,'github_token',''):
            raise ArchiveError('Set GITHUB_TOKEN in the private host configuration before exporting. Discord-only scans remain available.')
        headers = {"Authorization": f"Bearer {self.settings.github_token}",
                   "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        for attempt in range(3):
            try:
                async with self.session.request(method, self.base + path, json=payload, headers=headers,
                                                timeout=aiohttp.ClientTimeout(total=45), allow_redirects=False) as response:
                    if response.status >= 500 and attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    if response.status >= 300:
                        raise ApiError(response.status)
                    return await response.json()
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if attempt == 2:
                    raise ArchiveError("GitHub could not be reached; check your connection and retry.") from exc
                await asyncio.sleep(2 ** attempt)

    async def _read_manifest(self, commit):
        try:
            result = await self.request("GET", f"/contents/{MANIFEST}?ref={commit}")
        except ApiError as exc:
            if exc.status == 404:
                return {}
            raise
        try:
            if result.get("encoding") != "base64":
                raise ValueError()
            return parse_manifest(base64.b64decode(result["content"]).decode("utf-8"))
        except (ValueError, KeyError, UnicodeError) as exc:
            raise ArchiveError("Cannot read the existing archive manifest; nothing was uploaded.") from exc

    async def head(self):
        result = await self.request('GET','/git/ref/heads/'+quote(self.settings.branch,safe=''))
        return result['object']['sha']

    async def archive_proof(self):
        head = await self.head()
        commit = await self.request('GET',f'/git/commits/{head}')
        tree = await self.request('GET',f"/git/trees/{commit['tree']['sha']}?recursive=1")
        if tree.get('truncated'):
            raise ArchiveError('GitHub returned an incomplete tree. Cleanup is blocked; nothing was deleted.')
        # A symlink blob with matching text is not an archived Markdown file.
        blobs = {e['path']:e['sha'] for e in tree['tree']
                 if e['type']=='blob' and e.get('mode') in ('100644','100755')}
        return ArchiveProof(head,await self._read_manifest(head),blobs)

    async def index_into(self, store):
        """Read one immutable commit so concurrent GitHub writes cannot mix versions."""
        branch = quote(self.settings.branch, safe="")
        ref = await self.request("GET", f"/git/ref/heads/{branch}")
        head = ref["object"]["sha"]
        async def read(path):
            response = await self.request("GET", f"/contents/{quote(path, safe='/')}?ref={head}")
            if response.get("encoding") != "base64":
                raise ArchiveError("GitHub file encoding is unsupported.")
            return base64.b64decode(response["content"]).decode("utf-8")
        try:
            raw = await read(MANIFEST)
        except ApiError as exc:
            if exc.status == 404:
                return 0
            raise
        return await store.import_manifest(raw, read)

    async def publish(self, challenges):
        if not challenges:
            raise ArchiveError("No questions were collected. No GitHub files were changed.")
        branch = quote(self.settings.branch, safe="")
        for attempt in range(3):
            ref = await self.request("GET", f"/git/ref/heads/{branch}")
            head = ref["object"]["sha"]
            commit = await self.request("GET", f"/git/commits/{head}")
            tree = await self.request("GET", f"/git/trees/{commit['tree']['sha']}?recursive=1")
            if tree.get("truncated"):
                raise ArchiveError("The GitHub tree is too large to verify safely; no update was made.")
            existing = {e["path"]: e["sha"] for e in tree["tree"] if e["type"] == "blob"}
            previous = await self._read_manifest(head)
            # Manual edits to an imported prompt must not be silently overwritten.
            for entry in previous.values():
                for item in entry["files"]:
                    if existing.get(item["path"]) != item["sha"]:
                        raise ArchiveError("An imported question was edited or deleted manually. Reconcile its manifest entry before syncing.")
            files = archive_files(challenges, previous)
            managed = {f["path"] for e in previous.values() for f in e["files"]} | {MANIFEST, INDEX}
            for path in files:
                if path in existing and path not in managed:
                    raise ArchiveError("A new import would overwrite an unmanaged file; no update was made.")
            changes = [{"path": path, "mode": "100644", "type": "blob", "content": content}
                       for path, content in files.items() if existing.get(path) != git_blob_sha(content)]
            if not changes:
                return PublishResult(0, None, parse_manifest(files[MANIFEST]))
            new_tree = await self.request("POST", "/git/trees", {"base_tree": commit["tree"]["sha"], "tree": changes})
            new_commit = await self.request("POST", "/git/commits", {
                "message": f"Archive {len(challenges)} Cyber Skyline challenge prompts",
                "tree": new_tree["sha"], "parents": [head]})
            try:
                await self.request("PATCH", f"/git/refs/heads/{branch}", {"sha": new_commit["sha"], "force": False})
                return PublishResult(len(changes), f"https://github.com/{self.settings.repository}/commit/{new_commit['sha']}",
                                     parse_manifest(files[MANIFEST]))
            except ApiError as exc:
                if exc.status not in (409, 422) or attempt == 2:
                    raise
                latest = await self.request("GET", f"/git/ref/heads/{branch}")
                if latest["object"]["sha"] == head:
                    raise  # Policy rejection, rather than a concurrent commit.
                # Re-read, merge, and compare the new head before constructing another commit.
        raise ArchiveError("GitHub kept changing during the sync. Try again.")
