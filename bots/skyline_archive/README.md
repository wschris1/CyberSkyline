# Cyber Skyline Discord bot

Scan Cyber Skyline questions into season/competition/category/level folders on GitHub and get a Discord ping when a competition survey's website actually becomes usable.

The bot runs on your Windows PC or an always-on host. Discord controls it; GitHub stores the question archive. No AI subscription or model API key is required.

## What it does

| Command | Result |
| --- | --- |
| `/skyline sync event_url:<event overview URL>` | Scan one event and upload all accessible question prompts. |
| `/skyline sync preview:true event_url:<event overview URL>` | Check extraction and counts without uploading. |
| `/skyline sync-all` | Discover events on your Competition dashboard and scan those still accessible. |
| `/skyline stop` | Cancel the current scan or preview before GitHub publication starts. |
| `/skyline status` | Show progress, completion, upload link, or the reason a scan failed. |
| `/skyline watch-survey challenge_url:<survey challenge URL>` | Watch for its survey link, then check the actual website and ping you in this channel. |
| `/skyline survey-status` | Show your saved survey watches and what each is waiting for. |
| `/skyline unwatch-survey watch_id:<ID>` | Remove a watch. Remove it before intentionally rearming a finished watch. |

Commands work only in the configured server and only for the Discord user IDs in `DISCORD_OWNER_IDS`.

`/skyline stop` cancels the current scan and closes its browser without taking the
Discord bot offline. Wait until `/skyline status` says **Scan stopped** before
starting another scan. Collected questions from that run are discarded; an upload
that has already started cannot be cancelled or undone by this command. Survey
watches keep running, and any configured automatic scans still run on their next
scheduled interval. Start and status messages show whether the run is a preview.

## Windows setup

Use Python 3.10 or newer. Open PowerShell in the root of your downloaded/cloned `wschris-CyberSecurity` repository.

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r bots\skyline_archive\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item bots\skyline_archive\config.example.env bots\skyline_archive\.env
notepad bots\skyline_archive\.env
```

Run the `Copy-Item` command only for initial setup; keep an existing configured `.env`.

Fill in these settings locally:

| Setting | What to enter |
| --- | --- |
| `DISCORD_BOT_TOKEN` | Your application's bot token from the [Discord Developer Portal](https://discord.com/developers/applications). |
| `DISCORD_GUILD_ID` | Your Discord server ID. Enable Developer Mode in Discord, then use Copy Server ID. |
| `DISCORD_OWNER_IDS` | Your Discord user ID, or a comma-separated list of owners. |
| `GITHUB_TOKEN` | A [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) for this repository with **Contents: Read and write**. |
| `GITHUB_REPOSITORY` | Already set to `wschris1/wschris-CyberSecurity`. |
| `GITHUB_BRANCH` | Already set to `main`; this branch must exist and allow your token to commit. |
| `SKYLINE_EVENT_URL` | Optional event overview URL copied from Cyber Skyline. It has the form `https://cyberskyline.com/world/<event-id>`. |

Invite the Discord application to your server using the `bot` and `applications.commands` scopes. Give it **View Channels** and **Send Messages** in the channel where you want survey pings. It does not need Administrator, Server Members Intent, or Message Content Intent. If you use a thread, also allow **Send Messages in Threads**. Your own Discord notification preferences still determine whether a mention produces a push/sound.

Save your Cyber Skyline login once:

```powershell
.\.venv\Scripts\python.exe -m bots.skyline_archive login
```

A separate Chromium window opens. Sign in yourself, open the Competition dashboard so the event cards are visible, then return to PowerShell and press Enter. This creates a private browser session on your machine. Your normal Chrome session is not copied. If it expires, stop the bot, run `login` again, and restart it.

Check configuration and start:

```powershell
.\.venv\Scripts\python.exe -m bots.skyline_archive check
.\.venv\Scripts\python.exe -m bots.skyline_archive run
```

The terminal must stay running, and the host must stay awake and connected. `check` validates the configuration and presence of a saved session; it does not verify the tokens against Discord or GitHub. Slash commands register in the selected server when `run` connects.

## Survey opening later than its challenge

Run `/skyline watch-survey` in the channel where you want the ping. Copy the **Survey challenge page URL**, which has three IDs after `/module/`.

If the challenge already shows the actual survey website link, you can provide it explicitly:

```text
/skyline watch-survey challenge_url:<challenge URL> survey_url:<actual survey URL>
```

Without `survey_url`, the watcher reads the challenge prompt and looks for one survey/form link or embedded survey frame. If the prompt has several candidates, `/skyline survey-status` asks you to specify the right one. A blank challenge, missing link, unreachable website, closed form, or ordinary loading page remains in the waiting state.

The watcher checks about once a minute, plus page-loading time. It requires a successful website response and **visible, enabled form fields with a visible Next/Submit/Continue control**, on **two consecutive checks**, before mentioning you. The button may remain disabled until required fields are filled. A challenge marked open or an HTTP 200 response alone does not trigger a ping. Optionally set `ready_text` to a distinctive phrase from the survey title to narrow the check.

The watch survives restarts and sends one ping. It never fills out or submits the survey. If Discord delivery is interrupted at an uncertain point, the watch becomes `uncertain` instead of automatically risking a duplicate. Check the channel, then remove/rearm that watch if needed. Watches and tokens stay on the host, outside the GitHub archive.

Custom survey sites with unusual controls or a separate required login may need a small readiness adapter. No live competition survey was available during development; survey behavior is covered by synthetic tests and must be checked against your actual form once its URL is available.

## GitHub organization

Each question gets its own Markdown file, using this exact hierarchy:

`challenges/<season-year>/<competition-type>/<category>/<level>/<challenge-name>-qN.md`

For example:

```text
challenges/spring-2026/practice-game/forensics/easy/metadata-q1.md
challenges/spring-2026/practice-game/forensics/easy/metadata-q2.md
challenges/spring-2026/team-game/web/hard/example-challenge-q1.md
```

| Folder | Values |
| --- | --- |
| Season/year | `spring-2026`, `fall-2026`, and so on, read from the event title. |
| Competition | `gym`, `practice-game`, `individual`, `team-game`. |
| Category | `forensics`, `web`, `cryptography`, `osint`, `password-cracking`, and the other source categories. |
| Level | `easy`, `medium`, `hard`; `unrated` if the challenge supplies no difficulty. |
| Question file | One file per numbered question, including the shared challenge description. |

If two challenge titles would produce the same path, the bot adds the platform challenge ID to resolve the collision. The [generated question index](../../docs/skyline-questions.md) links every question. `archive-manifest.json` records managed files and content hashes. File paths remain stable if a challenge title changes. Events without a season/year or a recognized competition type are reported rather than filed under a guessed season.

Regular Q1/Q2 question tables and username/ciphertext tables are supported. Each question file includes the description, that question's text and point label, source challenge link, and referenced attachment names. Attachments, screenshots, training articles, solution guides, response cells, submission history, and personal scores are not uploaded. Existing authored guides under `challenges/<name>/` are retained alongside the season folders.

The public repository's existing policy is applied: common flag-like text, hash-like values, temporary instance URLs, and URL query values are removed. These redactions can remove part of a supplied example; use the original source challenge for the full input. Review a preview and export only content you have permission to archive or share. The importer cannot recognize every possible response-bearing string embedded in a prompt.

One successful batch produces one commit. Unchanged scans produce no commits. Closed/unavailable events are reported and never delete old imports. An unexpected page failure stops that batch before publication. Manually changed imported prompts or a reduction in source question count cause a conflict instead of silently overwriting/deleting files; keep authored notes in the existing guide folders or reconcile the managed manifest deliberately.

## Automatic archive scans

Set an event and a timer in `.env`, then restart the bot:

```dotenv
SKYLINE_EVENT_URL=https://cyberskyline.com/world/<your-event-id>
SYNC_INTERVAL_MINUTES=60
```

This scans the configured event on startup and every 60 minutes while running. `0` disables automatic archive scans. Survey watches have their own approximately one-minute polling cycle, independent of this timer. `/skyline sync-all` is manual so old, closed events are not continually retried.

## Private state and hosting

By default, browser login and watches are saved under `%LOCALAPPDATA%\skyline-archive` on Windows or `$XDG_DATA_HOME/skyline-archive` / `~/.local/share/skyline-archive` on Linux. `SKYLINE_STATE_DIR` can change that directory but cannot point into this repository. Do not upload `.env` or browser-state files. Run one bot instance per state directory; a process lock prevents accidental duplicates on the same host.

On a Linux host, install the same requirements and follow the [Playwright browser dependencies instructions](https://playwright.dev/python/docs/browsers#install-system-dependencies). The login command needs a graphical session. A service manager can keep `python -m bots.skyline_archive run` alive after setup. Automatic uptime/hosting is not provided by the repository itself.

## Validation and limits

Development checked the extractor against signed-in Cyber Skyline pages for both regular questions and ciphertext tables on November 3, 2026. Six regular questions and four ciphertext rows were found in the respective live checks. No questions were submitted and no challenge batch was published during development.

Automated standard-library tests cover URL restrictions, deterministic output, repeat scans, manifest conflicts, concurrent GitHub commits, survey readiness, restarts, and notification delivery ambiguity:

```powershell
py -3 -m unittest tests.test_skyline_archive -v
py -3 .github/scripts/check_challenges.py
py -3 -m unittest discover -s tests -v
```

Full Discord/GitHub runtime testing needs your configured bot and token. The development host could not install Chromium because its browser download was invalid; live DOM checks used the connected browser. Site layout changes, unavailable events, expired sessions, and unfamiliar survey forms are reported rather than treated as a complete scan.

API references: [Discord application commands](https://discordpy.readthedocs.io/en/stable/interactions/api.html), [Playwright authentication](https://playwright.dev/python/docs/auth), [GitHub Git trees](https://docs.github.com/en/rest/git/trees), and [GitHub references](https://docs.github.com/en/rest/git/refs).
