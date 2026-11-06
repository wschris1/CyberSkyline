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


SOURCE_REVISION = "fce310ba6ff86c4017c52c9b8a8ad09360bcb650"
SOURCE_ROOT = "https://raw.githubusercontent.com/wschris1/wschris-CyberSecurity/"
# SHA-256 values are filled by the release preparation script, not at runtime.
SOURCE_FILES = {
    'bots/__init__.py': 'c76016f913102f4ac56316fcf88a7e13a4fbdc381b38a2b192178359050fde65',
    'bots/skyline_archive/__init__.py': 'ccc2c70d57ce6880c6f89d56c141263260b47f9ddb4d443a5a4742a04ea575bf',
    'bots/skyline_archive/__main__.py': '705b9bb6486b38182d4438d73301c7a1d97337e2d458f7cd027494a9d6632acb',
    'bots/skyline_archive/ai_verification.py': '3e6fc5cd4f50caaa9e00458e00e73d3dd7fd6f797a80bd92c68a072d59994b6c',
    'bots/skyline_archive/attachments.py': 'bf95ea44955b9de7cbffcdbe40a6d458411a7a15b5897260783490408966a575',
    'bots/skyline_archive/bot.py': '8a08cb2708b7aa833bed4cec0aa4f7ecec9128db3ce475c9747137d360635502',
    'bots/skyline_archive/cleanup.py': 'a55ffbbbf29057b22260e9fad5232116d27443364d9118678281c6f6a810aa16',
    'bots/skyline_archive/cleanup_ui.py': 'e37aabc0c61ce516a1e68ba5dc935e6ba0cc1b18bbcc8a1ac056a65bd793376e',
    'bots/skyline_archive/core.py': 'f76bd527c432182ee4d057fc3ce01051de5e86cd3cfd9cc9e07b2f9ffa5f67f2',
    'bots/skyline_archive/discord_archive.py': 'e7597fe45427fa9acf3030eeaf92a575fcac31c51586673901d83726b2e2632b',
    'bots/skyline_archive/dom_extract.js': '050835ec858d9f64964d81b5e545e627e16ea6f109f5549960e1b6d51c558842',
    'bots/skyline_archive/github.py': '5dfa69bf6a0c719a30220deec49931de2473458fdb448ac2ef992e8fdd64eadb',
    'bots/skyline_archive/jobs.py': '73cd8b0e1be423f26bd05fee5c01d15302cd872d6c69fcd16927433d0ae916cb',
    'bots/skyline_archive/leaderboard.py': '880a28173f584833e7918e57040ccb0d93b0d9b2dfc3498bbe5f10b52f49626f',
    'bots/skyline_archive/leaderboard_dom.js': '77330935c15b68d27656c947e069227fb5186c660c7ebe6535df9ced28eff32d',
    'bots/skyline_archive/operations.py': '17f0328de930135e5ae56db79618c3addb85ecea382093c09219d60abd5595c6',
    'bots/skyline_archive/panel.py': '3843cf5e11645be9f9e68cb4a08e3ecc3051be1e6a136a224edee28619dc8935',
    'bots/skyline_archive/preferences.py': '0c6baf307d422903b8f26af745183133950b9cc8a2e2335ecb0a4c99c4dcd10b',
    'bots/skyline_archive/progress.py': '401f112bd354f362749abdb9ab761f27266edcf9d7b3b4c4c67e10bf7ac1b973',
    'bots/skyline_archive/scanner.py': '71f7362a75b5e708057bd3b304e6e40cdeabb6071b5a3e5cc02b7f5253018d05',
    'bots/skyline_archive/settings.py': 'a7328588f24b10c31df7e6e881789b5c71c47293ff049907073cb87fb21d548d',
    'bots/skyline_archive/storage.py': '890d3477164fbb4ec7e6a8707cfbf4c5042bfedcec0acbc76318ca091a829a4a',
    'bots/skyline_archive/survey.py': 'c682381988226b780fea2bd47a5713797eb0726b81049987080bc3cb467247b2',
    'bots/skyline_archive/ui.py': '1c37c41fae81f1076d703fc38a60bb305fc00b3aca5bd01c388ae16b4e663b65',
    'bots/skyline_archive/verification.py': '70fad9950d773e78e0afab9fc2b5435bc71382f06c28afcb3142db4a55bc4880',
    'bots/skyline_archive/verify_worker.py': '7b7c6a89d566e402706cde37030c46d2a597f062da0f39f0a659d6357d9bd9cb',
    'bots/skyline_archive/workflows.py': 'e68aa6b27f845a3f59049c61fafbd7fda36eaf4babea5c77f500bb254e21aae9',
    'bots/ws/__init__.py': '26fcbdf275d35ede6ee89f3267bdf2fbf677001e19de9c1858e9472a596c610b',
    'bots/ws/__main__.py': 'c463a563d2dff82bd997c6a50e5a26b07b2e3a5c824cde16acbb874ac4779cb9',
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
            headers={"User-Agent": "ws-archive-deployment"},
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
    print(f"WS host setup: Python {sys.version.split()[0]}", flush=True)
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
    required = ("DISCORD_BOT_TOKEN", "DISCORD_GUILD_ID", "DISCORD_OWNER_IDS")
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        message = "HOST READY: Python and Chromium passed. The Discord bot is not connected yet.\n"
        message += "SETUP NEEDED: " + ", ".join(missing) + f"\nEdit {config}.\n"
        (root / "setup-status.txt").write_text(message, encoding="utf-8")
        print(message, flush=True)
        return 0
    try:
        settings = load_settings(require_github=False)
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
    from bots.ws.__main__ import main as run_bot
    sys.argv = ["ws", "run"]
    run_bot()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SetupError, OSError, urllib.error.URLError, subprocess.TimeoutExpired) as error:
        print(f"SETUP FAILED: {error}", flush=True)
        raise SystemExit(1)
