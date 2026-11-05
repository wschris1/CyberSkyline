"""PebbleHost entry point: pinned source, Chromium preflight, then the Discord bot.

Upload this file and requirements.txt to the server root. No shell or root access
is required when the host already provides Chromium's system libraries.
"""

import asyncio
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request


SOURCE_REVISION = "f4149413fa1bdf8f7098172659af874ff28b8592"
SOURCE_ROOT = "https://raw.githubusercontent.com/wschris1/wschris-CyberSecurity/"
# SHA-256 values are filled by the release preparation script, not at runtime.
SOURCE_FILES = {
    'bots/__init__.py': 'c76016f913102f4ac56316fcf88a7e13a4fbdc381b38a2b192178359050fde65',
    'bots/skyline_archive/__init__.py': 'ccc2c70d57ce6880c6f89d56c141263260b47f9ddb4d443a5a4742a04ea575bf',
    'bots/skyline_archive/__main__.py': '74c93f4abc973b89e25f31a6c7ffc8ab612fd3baf1affc9bd981d9c729632fa9',
    'bots/skyline_archive/ai_verification.py': '3e6fc5cd4f50caaa9e00458e00e73d3dd7fd6f797a80bd92c68a072d59994b6c',
    'bots/skyline_archive/attachments.py': 'a1db2a781c891327a56d954b512c87024ddf74876d6f44e5166b574e94e01387',
    'bots/skyline_archive/bot.py': '4b8fd888edc97b0dc4ba60ef905f75566ff5b69f9893ed8e3192653966dde27f',
    'bots/skyline_archive/core.py': 'f76bd527c432182ee4d057fc3ce01051de5e86cd3cfd9cc9e07b2f9ffa5f67f2',
    'bots/skyline_archive/discord_archive.py': '3bcb02a2ad20ba4d7b22df871319513361f5d4d563d9bd0c581a682c523af9b3',
    'bots/skyline_archive/dom_extract.js': '050835ec858d9f64964d81b5e545e627e16ea6f109f5549960e1b6d51c558842',
    'bots/skyline_archive/github.py': '3568e6a96df23e853bbb4af0cc9aa82cb8fdf6deb35538b961113d41b637bd0e',
    'bots/skyline_archive/jobs.py': '124f30d2651952990cb69448aaa20aec0382c4458dc56fd565d3620dfc30b6d0',
    'bots/skyline_archive/operations.py': '3c490d6be6252edc6bb3f3f61c9d7bae3a8dc2357002c4d325530c81181e1fee',
    'bots/skyline_archive/preferences.py': '25bfc3481289d8f2d809618b3fbde7414046839b066ab001c3bcbfa24f489dc3',
    'bots/skyline_archive/progress.py': 'cc33be10254093ae2bfc5a7de12b39d9c707e7caad565aa73eb606607c08e13a',
    'bots/skyline_archive/scanner.py': '891d3dd91fb4eea1d97b1628876ab14136f645ea758d86e30bd21be5ebe92cd8',
    'bots/skyline_archive/settings.py': 'fbce643ac606980e289c65cdb8773a6325a6ced6f1d5c66e86059e769e2dbe75',
    'bots/skyline_archive/storage.py': '5da7da4716b737d1c437ffa58a3004bcd92c0974a1fc4568a5fca2782a9393e5',
    'bots/skyline_archive/survey.py': '86f2bef2980443f9e57439dc1e377b0de3a06b0d1ea3ed73fda949eaf037f4dc',
    'bots/skyline_archive/ui.py': '816374d576bd0bd00819cede2fd4f463ba887d1ed824fa07b25bf41051c518de',
    'bots/skyline_archive/verification.py': '44905dc6efaf6b776069c3d9127482e38763481ce0456daa26aa30c5febafc17',
    'bots/skyline_archive/verify_worker.py': '7b7c6a89d566e402706cde37030c46d2a597f062da0f39f0a659d6357d9bd9cb',
    'tools/__init__.py': '55fa407b33a3257258b0a3da6854fb83ac702260d8921c1f1cb025fd0ec593e7',
    'tools/_common.py': '33eda94911afe784e2fbc22731126ac8ca318db14f9eade5ae814f597a702a6f',
    'tools/artifact_inventory.py': '76ce149815cfdff979c3f238eb9a6aecbb94b6cc0d72e2765865b8f7818a7dce',
    'tools/decode_value.py': '1cdd1025c45ab3340bf4d87655bb7e9ae0c20e88d20f08fa11769a9127d6a02f',
    'tools/http_response_inspect.py': '0dbaf8926a600f105f5ad3ebae15532cf48500ad521994035f9ad48864971a82',
    'tools/image_metadata.py': 'd9143846eb8ca9f3ba3654d2ceecfddc744d6bb1970715e02f3185bc52b93840',
    'tools/pcap_summary.py': 'f24a1e78cc021c1327bca732613643ed1546f93eb39e25b3ff2d97668e422b96',
    'tools/strings_extract.py': '14078c9f0f7a7ba32d448a9e5e15cccce25d9256bac8d5399d30ac13805fadeb',
    'tools/timestamp_convert.py': 'b63cbdc2f06bf6d9e020f3565c23b7d5066e05b3b79f7212db00c103fbd227f4',
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
DISCORD_ARCHIVE_HUB_ID=0
DISCORD_NOTIFICATION_CHANNEL_ID=0
DEFAULT_PREVIEW=false
DISCORD_MESSAGE_CONTENT=false
OPENAI_API_KEY=
OPENAI_MODEL=gpt-5.4-mini
AI_VERIFY_ENABLED=false
AI_MAX_DAILY_REQUESTS=40
AI_MAX_OUTPUT_TOKENS=1600
AI_TIMEOUT_SECONDS=120
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


def save_browser_diagnostics(root):
    """Record only runtime and shared-library diagnostics, never environment secrets."""
    lines = [f"Architecture: {platform.machine()}"]
    release = Path("/etc/os-release")
    if release.is_file():
        lines.append(release.read_text())
    for tool in ("ldd", "apt-get", "apt-cache", "dpkg-deb"):
        lines.append(f"{tool}: {shutil.which(tool) or 'unavailable'}")
    binaries = sorted((root / "browser-cache").glob("chromium_headless_shell-*/**/chrome-headless-shell"))
    for binary in binaries:
        if shutil.which("ldd"):
            result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, timeout=30)
            lines.extend([str(binary), result.stdout, result.stderr])
    report = root / "chromium-check.txt"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Runtime diagnostic report: {report}", flush=True)


UBUNTU_LIBRARIES = {
    "libnspr4.so": "libnspr4", "libplc4.so": "libnspr4", "libplds4.so": "libnspr4",
    "libnss3.so": "libnss3", "libnssutil3.so": "libnss3", "libsmime3.so": "libnss3",
    "libatk-1.0.so.0": "libatk1.0-0t64", "libatk-bridge-2.0.so.0": "libatk-bridge2.0-0t64",
    "libatspi.so.0": "libatspi2.0-0t64", "libXcomposite.so.1": "libxcomposite1",
    "libXdamage.so.1": "libxdamage1", "libXtst.so.6": "libxtst6", "libXi.so.6": "libxi6",
    "libcups.so.2": "libcups2t64", "libpango-1.0.so.0": "libpango-1.0-0",
    "libcairo.so.2": "libcairo2", "libXcursor.so.1": "libxcursor1", "libXRes.so.1": "libxres1",
}


def missing_libraries(binary):
    result = subprocess.run(["ldd", str(binary)], capture_output=True, text=True, timeout=30)
    return set(re.findall(r"^\s*(\S+)\s+=>\s+not found", result.stdout, re.M))


def prepare_browser_libraries(root):
    """Extract official Ubuntu packages locally; never install as root or run scripts."""
    library_root = root / "browser-libs"
    local_path = str(library_root / "usr/lib/x86_64-linux-gnu")
    inherited = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = local_path + (":" + inherited if inherited else "")
    binaries = sorted((root / "browser-cache").glob("chromium_headless_shell-*/**/chrome-headless-shell"))
    if not binaries or not shutil.which("ldd"):
        return
    missing = missing_libraries(binaries[-1])
    if not missing:
        return
    release = platform.freedesktop_os_release()
    if (release.get("ID"), release.get("VERSION_ID"), platform.machine()) != ("ubuntu", "26.04", "x86_64"):
        raise SetupError("Automatic local library setup currently supports Ubuntu 26.04 x86_64 only.")
    if not all(shutil.which(tool) for tool in ("apt-get", "dpkg-deb")):
        raise SetupError("The host must supply the missing Chromium libraries.")
    downloads = root / "browser-packages"
    downloads.mkdir(exist_ok=True)
    log_path = root / "browser-libraries.log"
    apt_options = []
    with log_path.open("w", encoding="utf-8") as log:
        for attempt in range(4):
            unknown = missing - UBUNTU_LIBRARIES.keys()
            if unknown:
                raise SetupError("Unmapped browser libraries: " + ", ".join(sorted(unknown)))
            packages = sorted({UBUNTU_LIBRARIES[name] for name in missing})
            print("Preparing local browser libraries: " + ", ".join(packages), flush=True)
            command = ["apt-get", *apt_options, "download", *packages]
            result = subprocess.run(command, cwd=downloads, stdout=log, stderr=log, timeout=180)
            if result.returncode and not apt_options:
                # Use the host's configured, signed repositories and trust keys.
                # Only the package-index/cache/log destinations are redirected.
                apt_root = root / "browser-apt"
                for directory in ("lists/partial", "cache/archives/partial", "log"):
                    (apt_root / directory).mkdir(parents=True, exist_ok=True)
                apt_options = ["-o", f"Dir::State::lists={apt_root / 'lists'}",
                               "-o", f"Dir::Cache={apt_root / 'cache'}",
                               "-o", f"Dir::Log={apt_root / 'log'}"]
                print("Refreshing package indexes in the bot's own directory.", flush=True)
                update = subprocess.run(["apt-get", *apt_options, "update"], stdout=log, stderr=log, timeout=300)
                if update.returncode:
                    raise SetupError(f"Local package-index refresh failed; inspect {log_path}.")
                result = subprocess.run(["apt-get", *apt_options, "download", *packages],
                                        cwd=downloads, stdout=log, stderr=log, timeout=180)
            if result.returncode:
                raise SetupError(f"Library download failed; inspect {log_path}.")
            library_root.mkdir(exist_ok=True)
            for package in sorted(downloads.glob("*.deb")):
                extracted = subprocess.run(["dpkg-deb", "--extract", str(package), str(library_root)],
                                           stdout=log, stderr=log, timeout=60)
                if extracted.returncode:
                    raise SetupError(f"Library extraction failed; inspect {log_path}.")
            missing = missing_libraries(binaries[-1])
            if not missing:
                print("PASS: Chromium shared libraries resolved from local packages.", flush=True)
                return
    raise SetupError("Chromium still has missing shared libraries: " + ", ".join(sorted(missing)))


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
        prepare_browser_libraries(root)
        asyncio.run(browser_check())
    except Exception as exc:
        # The preflight uses only a synthetic page and no account credentials.
        print(str(exc), flush=True)
        save_browser_diagnostics(root)
        raise SetupError("Chromium preflight failed. The host may need additional Linux libraries.") from exc
    from bots.skyline_archive.core import ArchiveError
    from bots.skyline_archive.settings import load_settings
    required = ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID", "DISCORD_OWNER_IDS", "GITHUB_TOKEN")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        message = "HOST READY: Python and Chromium passed. The Discord bot is not connected yet.\n"
        message += "SETUP NEEDED: " + ", ".join(missing) + f"\nEdit {config}.\n"
        (root / "setup-status.txt").write_text(message, encoding="utf-8")
        print(message, flush=True)
        return 0
    try:
        settings = load_settings()
    except ArchiveError as exc:
        print("SETUP NEEDED: " + str(exc).replace("bots/skyline_archive/.env", "private/skyline.env"), flush=True)
        print(f"Edit {config}. Tokens are never printed by this setup script.", flush=True)
        return 0
    message = "HOST READY: Python and Chromium passed. Starting the Discord connection.\n"
    if not settings.auth_file.is_file():
        message += f"CYBER SKYLINE LOGIN NEEDED: upload your saved login to {settings.auth_file}.\n"
        message += "Discord commands can connect; challenge scans wait for the saved login.\n"
    message += "Service credentials are checked by the bot when used; check the console for connection results.\n"
    (root / "setup-status.txt").write_text(message, encoding="utf-8")
    print(message, flush=True)
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
