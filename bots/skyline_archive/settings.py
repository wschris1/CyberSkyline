"""Configuration and private paths, independent of the current working directory."""

from dataclasses import dataclass, field
import os
from pathlib import Path
import re

from .core import ArchiveError, skyline_url


REPO_ROOT = Path(__file__).resolve().parents[2]


def number(env, name, default, minimum, maximum):
    try:
        value = int(env.get(name, str(default)))
    except ValueError as exc:
        raise ArchiveError(f"{name} must be a whole number.") from exc
    if not minimum <= value <= maximum:
        raise ArchiveError(f"{name} must be between {minimum} and {maximum}.")
    return value


@dataclass(frozen=True)
class Settings:
    discord_token: str = field(repr=False)
    github_token: str = field(repr=False)
    guild_id: int
    owners: frozenset[int]
    repository: str
    branch: str
    event_url: str
    interval: int
    delay: int
    max_challenges: int
    state_dir: Path
    headless: bool

    @property
    def auth_file(self):
        return self.state_dir / "browser-state.json"

    @classmethod
    def from_env(cls, env=None, require_bot=True, require_github=True):
        env = os.environ if env is None else env
        token = env.get("DISCORD_BOT_TOKEN", "").strip()
        git_token = env.get("GITHUB_TOKEN", "").strip()
        if require_bot and not token:
            raise ArchiveError("Set DISCORD_BOT_TOKEN in bots/skyline_archive/.env.")
        if require_github and not git_token:
            raise ArchiveError("Set GITHUB_TOKEN in bots/skyline_archive/.env.")
        owners = env.get("DISCORD_OWNER_IDS", "").strip()
        if owners and not re.fullmatch(r"[0-9]+(?:\s*,\s*[0-9]+)*", owners):
            raise ArchiveError("DISCORD_OWNER_IDS must contain comma-separated numeric user IDs.")
        owner_ids = frozenset(int(x.strip()) for x in owners.split(",") if x.strip())
        if require_bot and (not owner_ids or 0 in owner_ids):
            raise ArchiveError("Set DISCORD_OWNER_IDS to your Discord user ID.")
        guild = number(env, "DISCORD_GUILD_ID", 0, 0, 2**64 - 1)
        if require_bot and not guild:
            raise ArchiveError("Set DISCORD_GUILD_ID to your Discord server ID.")
        repository = env.get("GITHUB_REPOSITORY", "wschris1/wschris-CyberSecurity").strip()
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ArchiveError("GITHUB_REPOSITORY must be owner/repository.")
        branch = env.get("GITHUB_BRANCH", "main").strip()
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", branch) or ".." in branch or branch.startswith("/"):
            raise ArchiveError("GITHUB_BRANCH is not a supported branch name.")
        event_url = env.get("SKYLINE_EVENT_URL", "").strip()
        if event_url:
            event_url = skyline_url(event_url)
        interval = number(env, "SYNC_INTERVAL_MINUTES", 0, 0, 10080)
        if interval and (interval < 60 or not event_url):
            raise ArchiveError("Timed sync needs SKYLINE_EVENT_URL and an interval of at least 60 minutes.")
        default = Path(env.get("LOCALAPPDATA") or env.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / "skyline-archive"
        state = Path(env.get("SKYLINE_STATE_DIR") or default).expanduser().resolve()
        if state.is_relative_to(REPO_ROOT):
            raise ArchiveError("SKYLINE_STATE_DIR must be outside the Git checkout.")
        headless = env.get("HEADLESS", "true").lower()
        if headless not in ("true", "false"):
            raise ArchiveError("HEADLESS must be true or false.")
        return cls(token, git_token, guild, owner_ids, repository, branch, event_url, interval,
                   number(env, "REQUEST_DELAY_SECONDS", 2, 1, 60),
                   number(env, "MAX_CHALLENGES", 2000, 1, 10000), state, headless == "true")


def load_settings(**kwargs):
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
    return Settings.from_env(**kwargs)
