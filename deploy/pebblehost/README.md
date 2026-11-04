# PebbleHost deployment

Use a Python bot-hosting service that supports Playwright's Linux browser dependencies.
In **Bot Settings**, select **Python**, **Python 3.12**, and start file **bot.py**.
Upload this directory's `bot.py` and `requirements.txt` to `/home/container`.
PebbleHost installs the requirements at startup.

Start once to download the pinned, SHA-256-verified application files and Chromium
headless shell. The startup script launches Chromium and tests a synthetic form.
It stops with `SETUP NEEDED` until credentials and the saved login are provided.
It does not make GitHub commits, send Discord messages, or access a competition
during this preflight. Missing Linux libraries must be supplied by the host.

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
