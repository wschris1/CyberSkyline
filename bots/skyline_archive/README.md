# WS — Cyber Skyline Discord bot

Scan Cyber Skyline questions into season/competition/category/level folders on GitHub and get a Discord ping when a competition survey's website actually becomes usable.

The bot runs on your Windows PC or an always-on host. Discord controls it; GitHub stores the public question archive, while a private database records Discord posts, question threads, files, settings and verification evidence. Local checks need no AI subscription or key. Optional OpenAI assistance uses a separately configured API key.

## What it does

| Command | Result |
| --- | --- |
| `/ws leaderboard link:<event leaderboard URL> time:10m` | Post the top 10, your signed-in player/team's rank and nearby competitors here, then repeat at your chosen interval. |
| `/ws leaderboard action:status` / `action:now` / `action:stop` | Inspect this channel's saved schedule, refresh once, or stop future leaderboard reports. |
| `/ws scan-discord event_url:<event overview URL> preview:false` | Fast competition workflow: stream collected challenges into Discord channels, question threads and files; no GitHub requests. |
| `/ws export-github` | Export saved source prompts from mapped Discord posts; optional channel/season/competition/category/difficulty filters. Works without a current Skyline login. |
| `/ws scan-both event_url:<event overview URL> preview:false` | Stream to Discord first, then export the prompt batch to GitHub. |
| `/ws cleanup preview` | Owner-only paginated cleanup plan. Verify every saved question against current GitHub files, then explicitly confirm Discord deletion. Optional season/competition/category/difficulty filters. |
| `/ws cleanup allow-recreate` | Allow matching retired archives to be built on future scans again. Does not recover deleted Discord discussions. |
| `/ws sync event_url:<event overview URL>` | Scan one event and upload all accessible question prompts. |
| `/ws sync preview:true event_url:<event overview URL>` | Check extraction and counts without uploading. |
| `/ws sync-all` | Discover events on your Competition dashboard and scan those still accessible. |
| `/ws stop` | Stop remaining collection/posting and preserve completed work. An in-flight GitHub commit finishes safely. |
| `/ws pause` | Save progress, close collection safely and hold scheduled checks. |
| `/ws resume` | Continue the latest paused/interrupted/stopped scan; release the schedule hold. |
| `/ws retry-failed` | Retry failed pages/publications using saved complete snapshots. |
| `/ws failures` | Privately browse saved failed challenges, reasons, source links and suggested fixes, including during an active scan. Optional `scan_id` selects an older run. |
| `/ws maintenance health test_ai:true` | Check source login, GitHub access, Discord permissions, cache and an optional small AI connection request. |
| `/ws evidence file:<upload>` | Associate supplemental evidence with this question; omit file to import your latest thread upload, or specify message_id. |
| `/ws hint` / `/ws explain` | Ask for an investigative hint or solving approach without a proposed answer. |
| `/ws maintenance reorganize preview:false` | Create separate challenge channels for existing archives, preserving and linking older discussions. Defaults to preview. |
| `/ws status` | Show current scan progress, authentication state and schedule. |
| `/ws pick` | Choose a scope, then Preview or Start scan. Defaults to Discord only; `destination:both` also exports to GitHub. |
| `/ws search keyword:<words>` | Search archived titles/question text; optional season, competition, category and difficulty filters. |
| `/ws maintenance reindex` | Index older manifest-managed GitHub questions locally without reposting them. |
| `/ws settings` | Change schedule, destinations, mappings, notifications and default preview in Discord. |
| `/ws session recheck` | Validate a refreshed session and unblock scans. |
| `/ws verify answer:<exact text>` | Check a proposed answer using local evidence, then optional OpenAI assistance if inconclusive. Omit `answer` to select a normal message. |
| `/ws survey watch challenge_url:<survey challenge URL>` | Watch for its survey link, then check the actual website and ping you in this channel. |
| `/ws survey status` | Show your saved survey watches and what each is waiting for. |
| `/ws survey unwatch watch_id:<ID>` | Remove a watch. Remove it before intentionally rearming a finished watch. |

Cleanup always starts with a preview, followed by a separate typed confirmation. Every question must match the configured GitHub branch; only verified archive channels and categories left empty qualify. **Deleting a channel also deletes its answers, discussions, threads and uploads, which are not backed up on GitHub.** Private cached files and verification records remain on the host. Scheduled scans do not immediately recreate retired archives. See [cleanup checks and recovery](../../docs/skyline-tracker.md#delete-discord-archives-already-exported-to-github).

Commands work only in the configured server and only for the Discord user IDs in `DISCORD_OWNER_IDS`.

## WS name and leaderboard dashboard

The bot is now **WS** and all commands begin with `/ws`. Survey controls are `/ws survey watch|status|unwatch`; health, reindex and reorganize live under `/ws maintenance`; cleanup is `/ws cleanup preview|allow-recreate`. The rest retain their existing command names, such as `/ws sync`, `/ws scan-discord`, `/ws settings` and `/ws verify`. Refresh Discord after upgrading to refresh its command list.

Run `/ws leaderboard link:<URL> time:10m` **in the text channel that should receive reports**. Use the specific event's Cyber Skyline `/world/<event ID>/leaderboard` link; an event overview link also works. Intervals accept `10`, `10m`, `30 minutes`, `1h`, or `1d` (1 minute–7 days). Each successful check sends a new report, even if the rank is unchanged. It includes source-ranked top 10, your signed-in player/team, points, accuracy, completion, nearby competitors, movement since the last report, the source link and check time. The optional `team:` is an exact-name check against the signed-in identity, not a search for arbitrary teams. Overall/all-modules is the source's default scope; custom bracket/module selection and public season-results pages are not supported by this reader.

One watch is saved per channel. Running the start command there again replaces its configuration and resets its movement baseline. `action:now` refreshes once, even if stopped; `action:stop` preserves prior messages; `action:status` shows the schedule and last issue. The first report is attempted immediately. Watches, due times, prior standings and pending sends live only in the existing private SQLite metadata, never in GitHub. Restart recovery checks recent message markers before repeating an uncertain send. Checks share the scan job slot on the 1 GiB host; a long scan can delay a report, and missed intervals are not replayed in a burst. A tick runs approximately every 15 seconds.

Unavailable/hidden/unopened standings produce a clear notice, then bounded retries; repeated failures do not create a notice each time. A known expired login blocks further source requests until `/ws session recheck` succeeds. Old scores are never relabeled as current. Unranked players are labeled as such with a theoretical rank when the source supplies one; the bot does not borrow another player's score or calculate ranks from points. Rank ties are determined by the source. Channel permissions are checked before saving and on each delivery. Active leaderboard destinations are protected from archive cleanup. Archive `DEFAULT_PREVIEW` and `/ws pause` do not disable a deliberately configured leaderboard schedule; use its own stop action.

The WS rename preserves the current database, session, private directory, GitHub manifest paths, channel/thread IDs and legacy post/topic markers. Existing `SKYLINE_EVENT_URL` and `SKYLINE_STATE_DIR` still work; optional `WS_EVENT_URL` and `WS_STATE_DIR` aliases take precedence. Do not move your state directory just to rename the bot. `python -m bots.ws` is the new CLI entry point; `bots.skyline_archive` remains a compatibility package. Existing historical messages are not mass-deleted or reposted; scans update editable bot instructions in place. The bot requests the WS username/server nickname on startup; the application name in Discord's Developer Portal should also be WS.

`/ws stop` stops remaining collection/Discord posting without taking the bot offline. Completed posts and discussions remain available; `/ws resume` continues the saved workflow. A GitHub commit already in progress cannot be cancelled safely. All workflows share one job lock. For the quickest competition setup, use `scan-discord`; export later with `export-github`. `scan-both`, legacy sync commands and existing schedules now finish Discord processing before GitHub. See [separate workflows](../../docs/skyline-tracker.md#separate-competition-workflows) for preview, filters and recovery semantics.

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
| `GITHUB_TOKEN` | Required for GitHub export only: a [fine-grained personal access token](https://github.com/settings/personal-access-tokens/new) for this repository with **Contents: Read and write**. |
| `GITHUB_REPOSITORY` | Already set to `wschris1/wschris-CyberSecurity`. |
| `GITHUB_BRANCH` | Already set to `main`; this branch must exist and allow your token to commit. |
| `SKYLINE_EVENT_URL` | Optional event overview URL copied from Cyber Skyline. It has the form `https://cyberskyline.com/world/<event-id>`. |

Invite the Discord application using the `bot` and `applications.commands` scopes. For progress, search and notifications, allow **View Channel**, **Send Messages**, **Read Message History**, and **Embed Links**. For the Discord question archive, also allow **Manage Channels**, **Manage Threads**, **Create Public Threads**, **Send Messages in Threads**, and **Attach Files**. Administrator is unnecessary. Existing destination overwrites can still deny these permissions; settings validate them before saving.

Normal-message answer selection additionally requires **Message Content Intent** in the Developer Portal and `DISCORD_MESSAGE_CONTENT=true` in the private environment, followed by a restart. Explicit `/ws verify answer:` and the answer modal work without that intent. Server Members Intent is unnecessary. Newly created archive categories are private to the bot and configured owners (server administrators can still see them); you can deliberately grant other roles access in Discord.

Read the [archive, settings and verification guide](../../docs/skyline-tracker.md) for the integrated workflow and limitations.
Save your Cyber Skyline login once:

```powershell
.\.venv\Scripts\python.exe -m bots.ws login
```

A separate Chromium window opens. Sign in yourself, open the Competition dashboard so the event cards are visible, then return to PowerShell and press Enter. This creates a private browser session on your machine. Your normal Chrome session is not copied. If it expires, refresh the login with this command on your desktop, replace the host’s private `browser-state.json`, then run `/ws session recheck`. If login and bot share one local state directory, stop that bot while running `login`. Known-invalid sessions pause scheduled source scans until recheck succeeds.

Check configuration and start:

```powershell
.\.venv\Scripts\python.exe -m bots.ws check
.\.venv\Scripts\python.exe -m bots.ws run
```

The terminal must stay running, and the host must stay awake and connected. `check` validates the configuration and presence of a saved session; it does not verify the tokens against Discord or GitHub. Slash commands register in the selected server when `run` connects.

## Survey opening later than its challenge

Run `/ws survey watch` in the channel where you want the ping. Copy the **Survey challenge page URL**, which has three IDs after `/module/`.

If the challenge already shows the actual survey website link, you can provide it explicitly:

```text
/ws survey watch challenge_url:<challenge URL> survey_url:<actual survey URL>
```

Without `survey_url`, the watcher reads the challenge prompt and looks for one survey/form link or embedded survey frame. If the prompt has several candidates, `/ws survey status` asks you to specify the right one. A blank challenge, missing link, unreachable website, closed form, or ordinary loading page remains in the waiting state.

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

Regular Q1/Q2 question tables and username/ciphertext tables are supported. Each question file includes the description, that question's text and point label, source challenge link, and referenced attachment names. Binary attachments, screenshots, training articles, solution guides, response cells, submission history, proposed answers and personal scores are not uploaded to GitHub. The optional private Discord archive downloads supported challenge attachments and links them from the challenge and question threads. Existing authored guides under `challenges/<name>/` are retained alongside the season folders.

The public repository's existing policy is applied: common flag-like text, hash-like values, temporary instance URLs, and URL query values are removed. These redactions can remove part of a supplied example; use the original source challenge for the full input. Review a preview and export only content you have permission to archive or share. The importer cannot recognize every possible response-bearing string embedded in a prompt.

One successful batch produces one commit. Unchanged scans produce no commits. Closed/unavailable events are reported and never delete old imports. Complete challenges publish even when other pages fail. Failed pages remain pending for `/ws retry-failed`. A challenge with incomplete or unrecognized question rows is never marked successfully archived. Conversational Launchpad challenges require submissions to reveal later questions; they remain explicitly unsupported and the bot never submits those replies. Manually changed imported prompts or a reduction in source question count cause a conflict instead of silently overwriting/deleting files; keep authored notes in the existing guide folders or reconcile the managed manifest deliberately.

## Automatic archive scans

Use `/ws settings` to choose a progress hub or notification channel, set a frequency (10–10080 minutes), and enable scheduled scans. Choose **Set frequency** and enter **10** for checks every ten minutes. A nonempty `SKYLINE_EVENT_URL` scopes them to that event; otherwise they discover all accessible events. The saved default preview applies to both manual and scheduled scans. Explicit `preview:true` / `preview:false` and picker buttons override it for one run.

Existing `SYNC_INTERVAL_MINUTES` and `SKYLINE_EVENT_URL` are still environment defaults. A positive environment interval requires an event URL; `0` defaults scheduling off. Saved settings override the corresponding environment defaults, survive restarts, and apply to the next run. The timer checks every 15 seconds and preserves its last scheduled start time. It waits while any scan, discovery, reindex or session check is active, and while login is known invalid. Existing installs need a progress destination selected before scheduled scans resume. Survey watches keep their separate polling cycle.

## Optional OpenAI answer assistance

The local verifier runs first. It now supports original EXIF creation timestamps
in JPEG, TIFF and PNG images, including questions asking to round down to the
minute. It compares original/digitized tags, reports conflicting dates, and never
substitutes the host's download/modification time. The result establishes a match
to embedded metadata, not that the camera clock was accurate. XMP, maker notes,
image pixels and arbitrary date conversions are not handled by this adapter.

When local checks are inconclusive, opt-in OpenAI assistance can inspect cached
files with the repository's metadata, file facts, text, strings, PCAP and saved
HTTP tools. It can select a local verification check, explain evidence, suggest
an unverified candidate and give a concrete next check. It cannot run arbitrary
commands, execute attachments, browse challenge sites or submit answers.
**Verified correct/incorrect** still requires a local check of the original
question and exact proposed answer. Otherwise the result remains **Inconclusive**,
with a separate AI assessment. Tool/API failures are **Verification error**.
Full long reports are attached privately to the thread.

On PebbleHost, add these entries to `/home/container/private/skyline.env` using
the private panel file editor, preserving existing entries:

```dotenv
OPENAI_API_KEY=<your-private-API-key>
OPENAI_MODEL=gpt-5.4-mini
AI_VERIFY_ENABLED=false
AI_MAX_DAILY_REQUESTS=40
AI_MAX_OUTPUT_TOKENS=1600
AI_TIMEOUT_SECONDS=120
```

Restart once to load the key. Run `/ws settings` and select **Toggle OpenAI
assistance**. This saved switch overrides `AI_VERIFY_ENABLED` and survives
restarts. Disable it from the same menu without restarting. Never paste an API
key into Discord, ChatGPT, logs or GitHub. Model and request limits are private
environment settings and require a restart. Choose a model your API project can
access; the configurable default is `gpt-5.4-mini`. API usage uses your OpenAI
project's billing/credits, and is not activated by the bot's Discord token.
The settings screen labels **scheduled scans** and **AI assistance** separately.
**API key loaded** confirms configuration only; a verification result whose
method says **OpenAI assisted** confirms a completed API response. A provider
error is reported explicitly. If no challenge files are cached, the model gets
their unavailable/oversized status without a file-inspection tool and explains
the missing evidence. This remains **Inconclusive**, not an incorrect answer.

AI runs only for owner-initiated verification, hint, explain, or an explicitly requested health connection test. Archive scans and survey watches do not use AI. Up to **4 API requests and 3 evidence tools per job**, **40 attempted
API requests per UTC day**, 1,600 output tokens per request and 120 seconds per
job are the defaults. Attempts count even if they fail, and the daily counter
persists in the existing private SQLite key/value storage. Set the daily limit
to 0 to block requests. These are request/token limits, not a dollar spending
cap; set any desired project budget/limits in OpenAI too. No automatic retries
increase the number of requests.

Enabling this sends the question, shared instructions, exact proposed answer,
filenames, availability status and bounded evidence excerpts to OpenAI. It does
not upload whole binary files or send Skyline sessions, bot tokens, server IDs or
host paths. Requests use `store:false`; this disables stored Responses, not all
provider retention. Text/string inspection covers only the first 8 KiB and marks
truncation. Images are inspected for metadata, not uploaded for visual analysis.
Large memory images, full packet-protocol analysis, OSINT browsing and arbitrary
code execution need separate tools. Missing files remain missing evidence.

Existing verification records already persist the answer, user, timestamp,
method, outcome and full evidence/AI explanation. Schema v3 adds scan checkpoints, question-location history, evidence associations and assistance records; existing verification records stay intact. Tests mock the API and use synthetic image metadata. An actual billed
OpenAI call must be checked after supplying your own key.

Primary references: [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling),
[Responses migration and storage](https://developers.openai.com/api/docs/guides/migrate-to-responses),
[GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini).

## Private state and hosting

By default, browser login, survey watches, the SQLite archive database and downloaded evidence are saved under `%LOCALAPPDATA%\skyline-archive` on Windows or `$XDG_DATA_HOME/skyline-archive` / `~/.local/share/skyline-archive` on Linux. `WS_STATE_DIR` (or the older `SKYLINE_STATE_DIR`) can change that directory but cannot point into this repository. Existing paths are retained through the WS rename. Do not upload `.env` or browser-state files. Run one bot instance per state directory; a process lock prevents accidental duplicates on the same host.

On a Linux host, install the same requirements and follow the [Playwright browser dependencies instructions](https://playwright.dev/python/docs/browsers#install-system-dependencies). The login command needs a graphical session. A service manager can keep `python -m bots.ws run` alive after setup. Automatic uptime/hosting is not provided by the repository itself.

## Validation and limits

The feature release is tested with synthetic files and mocked Discord, Skyline and HTTP fixtures. Tests exercise publication conflicts, deduplication, preview isolation, source IDs, category/channel/thread reuse, interrupted-send recovery, search permissions, migrations, settings, attachments, authentication, answer selection, verification outcomes and worker limits. They do not post to live Discord or submit competition answers.

```powershell
py -3 -m pip install -r bots/skyline_archive/requirements.txt
py -3 .github/scripts/check_challenges.py
py -3 -m unittest discover -s tests -v
```

The original extractor had live checks for regular and ciphertext question tables on November 3, 2026. That does not validate every competition page: unfamiliar layouts, missing access and page failures remain pending while complete challenges publish. This release still needs a deployment check of your host permissions, refreshed login, current page layouts, actual attachment delivery and live Discord interactions. Follow the [PebbleHost update instructions](../../deploy/pebblehost/README.md#upgrading-an-existing-ws-installation).

API references: [discord.py interactions](https://discordpy.readthedocs.io/en/stable/interactions/api.html), [Playwright authentication](https://playwright.dev/python/docs/auth), [GitHub Git trees](https://docs.github.com/en/rest/git/trees), and [GitHub references](https://docs.github.com/en/rest/git/refs).

## Challenge channels and recovery controls

Each source category contains one channel per challenge, such as **Open Source Intelligence → #meta-easy, #lookup-easy, #ssl-medium, #owasp-hard**. Each question gets its own parent message and thread. Same-named challenges from different events receive distinct channels. `/ws maintenance reorganize` previews migration of already posted archives; `preview:false` applies it. Discord cannot move an existing question thread to another parent/channel, so original discussions remain intact and new threads link to them. Verification still recognizes older mapped threads. Rescanning/reorganizing reuses IDs.

`/ws pause` holds scheduling across restarts and saves complete collected challenges. Streaming Discord publication can pause using saved post/thread checkpoints; an in-flight GitHub commit finishes safely. `/ws resume` reuses that checkpoint and progress message, skipping already published items. A crash also holds scheduling until resumed. `/ws stop` preserves completed posts and does not disable schedules. `/ws retry-failed` retries the latest failed run without reposting successful questions.

A future event shows **waiting for event** and the next check, reusing the same waiting message. Once its accessible challenges appear, a scheduled archive run attempts one owner ping and begins scanning. The event opening transition still needs checking when the actual event opens.

Private downloads default to **512 MiB per file / 2048 MiB total cache**, adjustable in `/ws settings`; old files are never deleted to meet a lowered budget. Downloads stream independently of Discord upload limits. Files over the server limit remain cached for analysis and are linked to the source challenge. The bot worker supports bounded facts/text/strings inspection of large files; deterministic checks remain limited to 64 MiB. Full memory-image analysis requires a separate stronger analysis environment.

Supplemental evidence is private and question-specific, never added to GitHub. `/ws evidence` imports only your own uploads from the current question thread. File imports from message history require Message Content Intent; the file option works without it. Hints/explanations use the same fixed evidence tools and daily API budget, are saved separately, and never update verified-answer status. Images are available for metadata inspection; visual image reasoning is not implemented. Team assignment/tracking is not included.
