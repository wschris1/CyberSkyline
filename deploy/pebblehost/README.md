# PebbleHost deployment

Use a Python bot-hosting service that supports Playwright's Linux browser dependencies.
In **Bot Settings**, select **Python**, **Python 3.12**, and start file **bot.py**.
Upload this directory's `bot.py` and `requirements.txt` to `/home/container`.
PebbleHost installs the requirements at startup.

Start once to download the pinned, SHA-256-verified application files and Chromium
headless shell. The startup script launches Chromium and tests a synthetic form.
It stops with `SETUP NEEDED` until the required credentials and Discord IDs are provided.
Once those are present, it connects to Discord even if the Cyber Skyline login is
still missing. Upload the saved login before scanning challenges; a missing login
is reported without taking the Discord commands offline.
It does not make GitHub commits, send Discord messages, or access a competition
during this preflight.

On Ubuntu 26.04 x86_64, missing supported libraries are downloaded from the host's
configured, signed Ubuntu repositories and extracted into `browser-libs`.
The bot uses these copies through `LD_LIBRARY_PATH`. This does not install system
packages, run package-maintainer scripts, use sudo, or change repository trust.
If package indexes are absent, an isolated `browser-apt` directory is used for
the index refresh. Other operating systems or unrecognized dependencies need
host support. Diagnostics are written to `chromium-check.txt` and
`browser-libraries.log`; these reports do not include credentials.

## Private configuration

The first start creates `/home/container/private/skyline.env`. Use the panel's
file editor to fill in `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`,
`DISCORD_OWNER_IDS`, and `GITHUB_TOKEN`, following the
[bot setup guide](../../bots/skyline_archive/README.md#windows-setup).
Never post tokens in chat, a support ticket, or GitHub.

Save a Cyber Skyline browser session on a computer with a graphical desktop using
the bot's `login` command. Upload **only that bot-created session file** through
the private panel/SFTP connection to
`/home/container/private/skyline-archive/browser-state.json`.
It grants account access; keep it private and replace it after session expiration.
Do not copy your regular browser profile.

The application is in `/home/container/skyline-app`, while credentials, browser
session, and survey watches remain in the separate `/home/container/private` tree.
Automatic archive scans remain off until an event URL and interval are configured.
Survey watches are added with the Discord slash command after startup.

## Updates and checks

`bot.py` pins the application revision and its file hashes. It refuses to replace
modified application files. To upgrade, preserve your existing files and deploy a
new verified application revision; keep the private directory and browser cache.
It does not automatically run new code from a moving Git branch.

The Chromium preflight establishes browser startup and local form interaction,
not successful login, Discord authorization, GitHub write access, or an actual
competition scan. Check those separately after private configuration is supplied.
