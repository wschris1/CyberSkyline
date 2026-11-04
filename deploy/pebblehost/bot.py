"""PebbleHost entry point: pinned source, Chromium preflight, then the Discord bot.

Upload this file and requirements.txt to the server root. No shell or root access
is required when the host already provides Chromium's system libraries.
"""

import asyncio
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request


SOURCE_REVISION = "4e70f8b63ac3012cb645eb7173f817fd5d0b4421"
SOURCE_ROOT = "https://raw.githubusercontent.com/wschris1/wschris-CyberSecurity/"
# SHA-256 values are filled by the release preparation script, not at runtime.
SOURCE_FILES = {
    'bots/__init__.py': 'c76016f913102f4ac56316fcf88a7e13a4fbdc381b38a2b192178359050fde65',
    'bots/skyline_archive/__init__.py': 'ccc2c70d57ce6880c6f89d56c141263260b47f9ddb4d443a5a4742a04ea575bf',
    'bots/skyline_archive/__main__.py': '74c93f4abc973b89e25f31a6c7ffc8ab612fd3baf1affc9bd981d9c729632fa9',
    'bots/skyline_archive/bot.py': '8abbfc610c355d3b17dc40f0b64e3f5854928e73698b581d584376e6bd591e34',
    'bots/skyline_archive/core.py': '9d3c92fe3fd83c1a57fbd9de1ffc55f33fb3aae6db9da77bb703eea06ea0eb8c',
    'bots/skyline_archive/github.py': '1ec55c0893ac94378cc8e814404181b83e1552fcda1681d19f322f31abdc62fb',
    'bots/skyline_archive/scanner.py': 'fdfbb4a4f2b57390c8ab69f08a6c38e39369c7092233886062ae493ea8a21bd9',
    'bots/skyline_archive/settings.py': 'c40f5ae8a818b7d412c596e0275da2d02ee82510ec96d7092c747bf529a96e9d',
    'bots/skyline_archive/survey.py': '22cfcb847dfcaa0878498b367c57772dbd413f93f2081b8da4a7146355ad9d0f',
    'bots/skyline_archive/dom_extract.js': 'e1ff43bec932818265cb932a338ebf913e34162f9e3926767f7f3defa71ed5cc',
}

CONFIG_TEMPLATE = """# Private configuration: enter secrets here, never in chat or GitHub.
DISCORD_BOT_TOKEN=
DISCORD_GUILD_ID=
DISCORD_OWNER_IDS=
GITHUB_TOKEN=
GITHUB_REPOSITORY=wschris1/wschris-CyberSecurity
GITHUB_BRANCH=main
SKYLINE_EVENT_URL=
SYNC_INTERVAL_MINUTES=0
REQUEST_DELAY_SECONDS=2
MAX_CHALLENGES=2000
HEADLESS=true
"""


class SetupError(Exception):
    pass


def install_source(root):
    """Download only missing, hash-verified files; preserve edited existing files."""
    app = root / "skyline-app"
    for relative, expected in SOURCE_FILES.items():
        destination = app / relative
        if not destination.resolve().is_relative_to(app.resolve()):
            raise SetupError("The application contains a path outside its directory.")
        if destination.exists():
            if hashlib.sha256(destination.read_bytes()).hexdigest() != expected:
                raise SetupError(f"Application file changed: {relative}. Preserve it before updating.")
            continue
        request = urllib.request.Request(
            f"{SOURCE_ROOT}{SOURCE_REVISION}/{relative}",
            headers={"User-Agent": "skyline-archive-deployment"},
        )
        with urllib.request.urlopen(request, timeout=45) as response:
            data = response.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024 or hashlib.sha256(data).hexdigest() != expected:
            raise SetupError(f"Source verification failed: {relative}.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(destination.suffix + ".download")
        try:
            temporary.write_bytes(data)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    return app


def prepare_private(root):
    private = root / "private"
    private.mkdir(mode=0o700, exist_ok=True)
    private.chmod(0o700)
    config = private / "skyline.env"
    try:
        with config.open("x", encoding="utf-8") as handle:
            handle.write(CONFIG_TEMPLATE)
    except FileExistsError:
        pass
    config.chmod(0o600)
    state = private / "skyline-archive"
    state.mkdir(mode=0o700, exist_ok=True)
    state.chmod(0o700)
    return config, state


async def browser_check():
    from playwright.async_api import async_playwright
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content('<title>Skyline preflight</title><form><input name="test"><button>Next</button></form>')
            await page.locator('input[name="test"]').fill("ready")
            if await page.locator('input[name="test"]').input_value() != "ready":
                raise SetupError("Chromium could not interact with the test form.")
            print("PASS: Chromium launched and interacted with a form.", flush=True)
        finally:
            await browser.close()


def main():
    if sys.version_info < (3, 10):
        raise SetupError("Select Python 3.12 in PebbleHost Bot Settings.")
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    print(f"Skyline host setup: Python {sys.version.split()[0]}", flush=True)
    app = install_source(root)
    print(f"PASS: application source verified ({SOURCE_REVISION[:12]}).", flush=True)
    config, state = prepare_private(root)
    try:
        from dotenv import load_dotenv
        import discord  # noqa: F401
        import aiohttp  # noqa: F401
        import playwright  # noqa: F401
    except ImportError as exc:
        raise SetupError("Install the supplied requirements.txt using the host's Python package manager.") from exc
    load_dotenv(config)
    os.environ.setdefault("SKYLINE_STATE_DIR", str(state))
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(root / "browser-cache"))
    sys.path.insert(0, str(app))
    print("Checking the Chromium download; an existing installation is reused.", flush=True)
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "--only-shell", "chromium"],
        check=False,
        timeout=600,
    )
    if result.returncode:
        raise SetupError("Chromium installation failed; see the download error above.")
    try:
        asyncio.run(browser_check())
    except Exception as exc:
        # The preflight uses only a synthetic page and no account credentials.
        print(str(exc), flush=True)
        raise SetupError("Chromium preflight failed. The host may need additional Linux libraries.") from exc
    from bots.skyline_archive.core import ArchiveError
    from bots.skyline_archive.settings import load_settings
    try:
        settings = load_settings()
    except ArchiveError as exc:
        print(f"SETUP NEEDED: {exc}", flush=True)
        print(f"Edit {config}. Tokens are never printed by this setup script.", flush=True)
        return 0
    if not settings.auth_file.is_file():
        print(f"SETUP NEEDED: upload your saved Cyber Skyline login to {settings.auth_file}.", flush=True)
        return 0
    print("Starting the Discord bot. Service credentials are checked by the bot when used.", flush=True)
    from bots.skyline_archive.__main__ import main as run_bot
    sys.argv = ["skyline-archive", "run"]
    run_bot()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SetupError, OSError, urllib.error.URLError, subprocess.TimeoutExpired) as error:
        print(f"SETUP FAILED: {error}", flush=True)
        raise SystemExit(1)
