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
Automatic archive scans remain off until enabled through `/skyline settings` or
the existing environment interval. Configure a progress destination before enabling them.
Survey watches are added with the Discord slash command after startup.

## Upgrading an existing NCL TRACKER installation

Use the server's private panel file manager/SFTP connection. These steps keep the
existing login, survey watches, mappings, questions and discussion intact.

1. In Discord, use `/skyline pause` on releases that support it (otherwise `/skyline stop`) if collection is running. If publication has
   started, wait for `/skyline status` to finish. Then press **Stop** in PebbleHost
   and wait until the process is offline.
2. Back up the root `bot.py`, `requirements.txt`, and the **entire**
   `/home/container/private` directory to a private location. Include
   `archive.sqlite3`, any `-wal`/`-shm` sidecars, `survey-watches.json`,
   `browser-state.json`, evidence files and `skyline.env` if present. Keep this
   backup private; it contains credentials and proposed answers.
3. Rename `/home/container/skyline-app` to an unused backup name such as
   `skyline-app-before-tracker-update`. Preserve it rather than overwriting
   modified source. Keep `private`, `browser-cache`, `browser-libs` and
   `browser-apt` where they are.
4. Download the new [bot.py](https://raw.githubusercontent.com/wschris1/wschris-CyberSecurity/main/deploy/pebblehost/bot.py)
   and [requirements.txt](https://raw.githubusercontent.com/wschris1/wschris-CyberSecurity/main/deploy/pebblehost/requirements.txt).
   Upload those two files to `/home/container`, replacing the root copies.
   The loader pins an immutable application revision and SHA-256 hashes,
   including the repository tools used for verification.
5. In Bot Settings, keep **Python 3.12** and startup file **bot.py**. Preserve the
   existing private environment. To select normally typed answers, enable
   **Message Content Intent** for the bot in the Discord Developer Portal and
   add `DISCORD_MESSAGE_CONTENT=true` to `/home/container/private/skyline.env`.
   Without it, explicit `answer:` and the answer modal still work. Keep
   `DEFAULT_PREVIEW=true` as an optional initial environment default; an
   existing saved preview setting takes precedence.
6. Grant the bot **View Channel**, **Send Messages**, **Read Message History**,
   **Embed Links**, **Attach Files**, **Manage Channels**, **Manage Threads**,
   **Create Public Threads**, and **Send Messages in Threads** in the server
   and intended destinations. Administrator is unnecessary. Existing channel
   overwrites can still deny permissions.
7. Press **Start**. The loader downloads the pinned application/helpers, verifies
   hashes, installs/checks Chromium, and starts the bot. New SQLite migrations
   run automatically. Check the console, `setup-status.txt` and
   `chromium-check.txt`; do not share the private environment or session file.
8. In Discord run `/skyline settings`: choose an archive hub and notification
   channel, enable the Discord archive, and turn **default preview** on for
   the first check. Keep scheduling off until the checks below succeed.
   Existing category/channel IDs remain mapped; new installs create only
   missing categories and challenge channels.
9. Run `/skyline reindex` for older GitHub imports, `/skyline session recheck`,
   and `/skyline pick`. Choose one small scope and **Preview**. Confirm the
   scope, permissions and extraction results before pressing **Start scan**.
   If login is invalid, use your existing desktop login workflow, replace
   `/home/container/private/skyline-archive/browser-state.json`, and recheck.

For a live deployment check, scan one challenge, inspect its instructions,
question parent, thread and file links, then scan it again to confirm reuse.
Test search as an owner with the intended channel access. Run a supported
verification in its question thread, confirm the exact answer/result and parent
status, then restart and repeat search to check persistence. Verify survey
readiness separately when an actual form is available. Finally set default
preview and scheduled scanning as desired. These live checks are not performed
by the mocked test suite or the Chromium preflight.

If an upgrade fails, stop the bot before recovery. Keep the current private
directory as a second backup. Restore matching application/loader files and a
compatible private-state backup; never point an older SQLite-aware release at a
newer unsupported database. Restoring an older database after newer Discord
posts were sent loses their mappings and can create duplicates—reconcile those
IDs before scanning. Do not delete existing Discord questions or threads to
troubleshoot a code update.

See the [workflow guide](../../docs/skyline-tracker.md) for command examples,
settings precedence, file limits, recovery and verification methods.

## Updates and checks

### Recovering a missing database after a host transfer

Restore the complete private directory from a recent backup whenever possible.
If no database backup remains, `recover.py` can rebuild links from the GitHub
manifest, currently accessible source questions, and this bot's existing Discord
archive markers. Stop the regular bot, back up the new server, deploy the current
`bot.py` and `requirements.txt`, and preserve/rename any outdated `skyline-app`.
Put `recover.py` beside `bot.py`, then temporarily select it as the start file.
It needs the same private configuration, saved login, and Message Content Intent.

Recovery reads the source, downloads available evidence and rebuilds the local
database; it never posts, edits, deletes or submits remote archive content.
Duplicate markers, missing threads, source errors, and bounded history limits
stop recovery for review. After `RECOVERY COMPLETE`, select `bot.py` again and
restart. Review `/skyline settings` before enabling the archive or scheduled
scans. Preview remains on and scheduling/AI remain off. A count-only report is
saved as `private/skyline-archive/host-recovery-report.json`.

This is not a full database restore: missing scan history, settings and survey
watches cannot be inferred. Short verification results can be recovered with
their exact answers and timestamps, but their original submitter is stored as
unknown (`user_id=0`). Long reports remain accessible in the original threads.
Existing discussions, archived threads, and uploaded Discord files are preserved.
The bot's file markers bind uploads to their original source hashes. If Discord
stored an image with a different byte size, recovery records that difference and
keeps the existing upload; verification reads the newly cached source original.

### Enable OpenAI assistance after upgrading

The release includes the OpenAI connector and EXIF creation-date adapter. No new
Python package is required. Keep the existing private database and artifacts.
Add `OPENAI_API_KEY=<your private key>` and `OPENAI_MODEL=gpt-5.4-mini` to
`/home/container/private/skyline.env`, then restart. In Discord, open
`/skyline settings` and select **Toggle OpenAI assistance**. Verify a question in
its existing thread. The key is never entered in a Discord command.

The switch is off by default. Saved preferences take precedence over
`AI_VERIFY_ENABLED`. Local checks, scans and survey watches continue to work
without a key. See [data sharing, request limits and supported evidence tools](../../bots/skyline_archive/README.md#optional-openai-answer-assistance).
Changing the model or private key requires a restart; toggling AI does not.

### Loader behavior

`bot.py` pins the application revision and its file hashes. It refuses to replace
modified application files. To upgrade, preserve your existing files and deploy a
new verified application revision; keep the private directory and browser cache.
It does not automatically run new code from a moving Git branch.

The Chromium preflight establishes browser startup and local form interaction,
not successful login, Discord authorization, GitHub write access, or an actual
competition scan. Check those separately after private configuration is supplied.

### Scan-control and challenge-channel release

This update requires no dependency or credential changes. Preserve the entire private tree before replacing the pinned loader/application. Startup migrates SQLite to v3 and keeps a pre-migration SQLite backup. After restarting, run `/skyline health test_ai:true`, then `/skyline reorganize` to preview existing-archive migration and `/skyline reorganize preview:false` to apply it. Old discussions remain linked; no answers are deleted. Run reorganization again after interruption to reuse the saved IDs. Do not use an older recovery loader against v3 state. The standalone `recover.py` reconstructs legacy layouts only; for v3 restore the full private backup.

Use `/skyline resume` after a paused/interrupted scan to release the persistent schedule hold. Confirm `/skyline settings` shows scheduled scans enabled, frequency 10, the intended default preview, and your archive/notification destinations. A not-yet-open event should show waiting, not failure. After one small archive run verify its challenge channel, question threads, old-discussion links, file statuses and search results; repeat to check reuse. Survey opening and actual competition opening remain event-dependent checks.
