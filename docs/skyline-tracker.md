# WS archive workflow

The bot and slash-command root are now **WS**. Use `/ws leaderboard link:<event leaderboard URL> time:10m` in the destination text channel to receive recurring standings and your signed-in player/team's position. `action:status`, `action:now` and `action:stop` manage that channel's watch. See [leaderboard setup, persistence and limits](../bots/skyline_archive/README.md#ws-name-and-leaderboard-dashboard). Existing archive data and private paths are retained. Survey commands are grouped under `/ws survey`; health, reindex and reorganize are under `/ws maintenance`; cleanup is under `/ws cleanup`.

WS retains its GitHub importer, preview mode, survey watches, timer and owner checks. The Discord archive is an additional destination. All `/ws` commands and their controls remain restricted to `DISCORD_OWNER_IDS` in `DISCORD_GUILD_ID`; component interactions also check the initiating owner. Local checks need no additional service. Optional OpenAI assistance requires its own private API key.

## First use

1. Follow the [PebbleHost upgrade instructions](../deploy/pebblehost/README.md#upgrading-an-existing-ws-installation), including the additional Discord permissions.
2. Open `/ws settings`, select an archive hub for progress and a notification destination, then enable the Discord archive. The hub is a control/progress channel; questions go in challenge channels.
3. Run `/ws maintenance reindex` to index existing manifest-managed GitHub questions. This creates no Discord posts or successful-sync markers. Legacy results link to GitHub until you deliberately scan their source into Discord.
4. Run `/ws session recheck`, then `/ws pick`. Select season, competition, category and difficulty; each stage supports pages of 24 options plus All. The final screen shows the scope and separate **Preview** and **Start scan** buttons. **Scan everything…** preserves the all-events workflow.
5. Preview first. Start scan deliberately when its scope is right. `/ws sync` and `/ws sync-all` still accept `preview:true`; `/ws stop` cancels remaining collection/Discord work and preserves already created posts.

Discovery reads accessible event/module pages using the saved session. A scan rediscovers the selected scope so a stale picker cannot silently include the wrong event. Unknown totals display as unknown; no percentage or ETA is fabricated. Known-total scans show processed challenges, new/changed versus already-synced local snapshots, failures, file progress and elapsed time. An approximate ETA appears only after three processed challenges and ten seconds of collection; it estimates the remaining scan phase, not GitHub/Discord delivery. Unavailable events are reported separately. New/unchanged counts refer to local challenge snapshots, not new message counts.

Each run uses one durable Discord progress message, edited at most every five seconds during work, with an immediate final update. `/ws status` remains usable if that message is deleted or an edit fails. Only one scan/discovery/reindex/login check runs at a time. A process lock prevents two instances using the same local state directory. Run only one host against an archive; separate hosts with copied state are not a distributed lock.

Preview reads source pages and saves only run diagnostics, never archive categories, channels, posts, threads, binary downloads, GitHub commits or successful-sync markers. Its plan uses saved mappings and question counts; it reports that deleted Discord objects may need repair and that attachment sizes/downloadability were not checked. Preview is not a guarantee that subsequent permissions or network operations will succeed.

## Separate competition workflows

| Command | What it does |
| --- | --- |
| `/ws scan-discord` | Collect the configured event and immediately queue each complete challenge for Discord categories, individual challenge channels, question posts, threads and files. Never contact GitHub. |
| `/ws export-github` | Check mapped Discord question parents, then export their saved source prompts to GitHub. Never revisit Cyber Skyline or read answer discussions. |
| `/ws scan-both` | Run the same streaming Discord scan, then publish the collected prompt batch to GitHub after Discord processing finishes. |

For an opening competition, use `/ws scan-discord event_url:<world URL> preview:false`. Use `all_events:true` instead of `event_url` for every accessible event. Both scan commands honor the saved preview default and accept an explicit override. They require the Discord archive to be enabled. `/ws pick destination:discord` is the interactive equivalent (and the picker's default); choose `destination:both` for combined publication. Existing `/ws sync` and `/ws sync-all` remain combined aliases and retain their legacy GitHub-only behavior if Discord archiving is disabled.

Source pages are collected serially using the configured request delay. A single independent Discord publisher starts after the first complete challenge and its downloads are captured; it creates question threads while later pages are still being collected. The private SQLite queue is saved before posting. This avoids waiting for the entire event or any GitHub request before the first archive appears, while preventing simultaneous category/channel creation races. Large source downloads and Discord rate limits can still delay a challenge; this is not an instant or unlimited-parallel scan. Progress separates source items from completed Discord archives and the challenge currently being posted.

Export defaults to all mapped archived challenges. Optional `channel`, `season`, `competition`, `category` and `difficulty` filters narrow it; season uses `fall-2026`, competition uses `gym`, `practice-game`, `individual` or `team-game`. The bot checks each recorded parent exists and is a managed bot post. It exports the original structured source snapshot, not edited Discord message bodies, user messages, answers, verifications or attachments. Missing/unreadable parents are reported for repair; successful archives can still export. Unposted local snapshots are excluded. This command works while a Skyline session is known invalid. The SQLite archive must remain available; it does not reconstruct a lost database from arbitrary chat.

A GitHub failure leaves Discord posts and threads intact and appears in `/ws failures`. Run `/ws export-github` later or retry the failed combined run. GitHub's existing manifest compares content and prevents duplicate commits. Independent destination fingerprints are saved only after that destination succeeds; Discord success never implies a GitHub upload. GitHub credentials are optional for starting the bot and Discord-only operation, and required when exporting. Existing schedules retain their combined behavior, now with Discord first; a manual Discord-only run does not disable scheduled exports. All three commands share the scan lock and effective settings.

Preview on either scan command makes no Discord archive writes or GitHub calls. Export preview checks mapped parents and reports how many source question files would be considered, without downloading, posting, committing or recording export success; exact changed-file counts require comparing GitHub during actual export. Stop/pause can interrupt Discord delivery safely using its existing pending-send recovery records. Already posted work stays available. A GitHub commit already in progress finishes before a pause takes effect. Resume and retry retain the saved workflow and filters across restarts.

## Categories, questions and recovery

Source categories become Discord categories. Each challenge becomes its own text channel, for example **Open Source Intelligence → #meta-easy, #lookup-easy, #ssl-medium**. Multiple Easy challenges never share a channel. A missing difficulty uses `unrated`. Stable source event/challenge/question identifiers are retained with season, competition, category and difficulty. Same-name challenges from different events stay distinct.

Within each challenge channel the bot uploads files, posts challenge instructions, then posts each question and creates a public thread attached to that parent. Every parent includes the question number, complete source question text, any supplied point label, context, instructions/files links and a discussion link. Each thread repeats the complete question, instructions and file links. Long text uses ordered continuation messages to fit Discord limits.

The private database records category/channel mappings, challenge and question IDs, post IDs, file hashes, parent messages, threads and verifications. Rescans update managed text and reuse saved IDs. They do not remove user replies or discussions. Unlocked archived threads reopen when needed. Locked threads require an owner to unlock them. If a parent disappears but its thread survives, the replacement parent links to that existing discussion. A deleted thread can be recreated, but its deleted discussion cannot be recovered.

Before sending a managed archive post, the bot journals a pending record and adds a deterministic footer marker. After a crash it searches the original channel for that marker before sending again. If more than 2,000 messages make delivery ambiguous, it stops for reconciliation instead of risking a duplicate. Interrupted runs are marked on restart and hold scheduled checks. `/ws resume` continues the saved queue and complete snapshots using the same progress message. `/ws pause` saves work and holds scheduling across restarts; `/ws stop` cancels collection without disabling scheduling. `/ws retry-failed` retries failed pages/publications and retains successful items. Streaming Discord publication may pause mid-challenge; saved post/thread IDs and pending-send markers are reused on resume. A GitHub commit already in progress finishes safely before pause. A source question count reduction or replacement of known question identities stops for reconciliation instead of reassigning old discussion.

Category creation also journals its intent. An unrelated, already-existing category with the same name requires an explicit mapping in settings. Challenge channels store the source identity in their topic and database mapping for recovery after a create-before-save crash. Same-name challenges in other events get a stable identity suffix. A full Discord category is reported explicitly for owner remapping. `/ws maintenance reorganize preview:false` migrates already posted archives to the new layout. Old parents/threads and their discussions remain; new canonical threads link back. Older thread IDs remain valid for verification. A deleted channel may need a replacement. No discussion is deleted or physically moved.

## Search

Use `/ws search keyword:<words> season:<spring-2026> competition:<practice-game> category:<Password Cracking> difficulty:<easy>`. Filters are optional and case-insensitive; keywords match whole indexed words with AND semantics. Competition values are `gym`, `practice-game`, `individual`, and `team-game`.

SQLite FTS5 indexes locally archived titles and question text, including older imports added through `/ws maintenance reindex`. Pages contain snippets and direct links to existing question posts, accessible threads and available GitHub files. Channel **View Channel** and **Read Message History** permissions are checked for the requesting member before filtering/pagination and rechecked on each page. Missing or inaccessible channels are excluded. GitHub-only legacy entries are visible only to the configured owners. Search does not inspect answers or discussion messages.

## Files

Recognized Cyber Skyline `/artifact/` links are downloaded using cookies scoped to their original HTTPS host. Redirects are limited and public destinations validated. Session cookies, authentication headers and credential-bearing download URLs are never posted or logged. Discord fallbacks link to the source challenge, which may require your login.

Downloads stream in 64 KiB chunks with a 600-second total timeout and 45-second stalled-read timeout. Defaults are 512 MiB per file and 2048 MiB for the private cache, configurable in settings. The bot reserves 128 MiB of disk headroom and serializes downloads; an exhausted budget fails clearly without deleting existing evidence. Names retain recognizable text while removing path traversal, control characters and device names. Cache identity uses the source challenge and artifact path, with SHA-256 content hashes. ETag/Last-Modified validators avoid re-downloading unchanged data; sources without validators are rechecked after 24 hours. Unchanged content reuses its uploaded message. Temporary files are removed after success/failure/cancellation and at restart; content-addressed evidence files remain private for verification and history.

Every upload checks the destination guild's current `filesize_limit`. Oversized, unavailable and failed files retain explicit statuses and source links. Attachment failure does not mark an answer incorrect or discard the question archive; rerunning retries files. Relevant shared files are linked both from challenge posts and question parents/threads. Unrecognized external download layouts need an explicit adapter. The bot does not execute downloaded files or commit them to GitHub.

## Session refresh

A missing/malformed session, HTTP 401, sign-in redirect or displayed sign-in form is an authentication failure. HTTP 403, timeouts, page-layout changes and ordinary service failures are not automatically classified as expired credentials.

Known-invalid login blocks manual/scheduled source scans (but not `/ws export-github`) and source-based survey polling until recheck. Existing direct survey URLs can continue their normal readiness checks. One login alert is attempted through the configured notification destination, falling back to the progress hub/current command channel. The alert is recorded before sending, so ambiguous delivery does not spam after a restart. If delivery failed, `/ws status` still reports the blocked session.

Use the existing desktop `python -m bots.ws login` workflow, upload its `browser-state.json` to the host's private state directory, then run `/ws session recheck`. A successful validation clears the block and alert latch. A network failure during recheck retains the previous authentication state. No already-archived content is removed.

## Settings and precedence

`/ws settings` provides channel selectors, toggles, frequency/prefix/file-budget inputs and category/challenge mapping inputs. For category mappings provide the exact source category and destination category ID. For a challenge channel provide its source challenge URL and a text channel ID; one channel cannot be mapped to two challenges. Legacy difficulty mappings remain stored for compatibility, but new challenge channels do not use them. Changes take effect on the next scan/reorganization and retain linked older discussions. Values, server identity and required permissions are validated before save. Configure destinations before enabling scheduling or the Discord archive. Controls last ten minutes; reopen the command after expiry or a restart.

| Setting | Initial default | Saved behavior |
| --- | --- | --- |
| Automatic scans | Off; `SYNC_INTERVAL_MINUTES` can enable for `SKYLINE_EVENT_URL` | Saved enabled toggle and 10–10080 minute interval override environment defaults |
| Scope for automatic scans | `SKYLINE_EVENT_URL` if configured, otherwise all accessible events | Manual picker selections apply only to their run |
| Discord archive | Off unless `DISCORD_ARCHIVE_HUB_ID` is set | Toggle separately from GitHub publication |
| Archive/progress hub | `DISCORD_ARCHIVE_HUB_ID`, or invocation channel for manual progress | Saved channel applies to future progress; old archive mappings remain |
| Notifications | `DISCORD_NOTIFICATION_CHANNEL_ID`; login alerts on, completion alerts off | Saved destination/preferences override defaults; survey watches retain their own destination |
| Default preview | `DEFAULT_PREVIEW=false` | Saved default applies to manual and scheduled scans; explicit preview/start overrides it |
| Category prefix/mappings | Empty prefix; source category/challenge identities | Private persisted IDs; older discussions retained and linked |
| File/cache budgets | 512 / 2048 MiB | Saved values apply to future downloads; existing files are not deleted |

Saved settings override their corresponding environment values on every restart. Changes are refused while a scan/discovery/reindex/login check is active and apply on the next run; both manual and scheduled runs read the same effective preferences. Disabling schedules does not cancel an active scan—use `/ws stop` to stop remaining work. Secrets, owner IDs, server ID, session location and Message Content Intent remain private environment configuration and require restart when changed. The interface cannot grant owners or expose tokens.

## Independent verification

Inside a mapped question thread use `/ws verify answer:<exact text>`. With Message Content Intent enabled, `/ws verify` can use your sole unambiguous answer message since your last verification (within the latest 100 thread messages). Multiple candidates require selection; no candidates opens an answer input. Other users' messages and bot messages are excluded. If the desired message is older, provide it explicitly.

The bot displays the exact proposed answer as a JSON string (escaped newlines/tabs represent those original characters), or as a UTF-8 attachment for long answers. It does not trim, case-fold or reinterpret answer data unless the method explicitly allows it, such as hexadecimal digest letter case. Plain typing alone never submits or checks an answer.

| Supported evidence | Method and limits |
| --- | --- |
| Explicit unsalted MD5/SHA-1/SHA-256/SHA-512 password digest | Hash exact UTF-8 proposed bytes against one unambiguous supplied digest; no brute force |
| Encrypted ZIP password | Python ZipCrypto support; decrypt/read every encrypted member and check CRCs, without extracting; unsupported encryption is an error |
| Direct Base64/Base64url/hex decoding | `tools/decode_value.py`, one input up to 64 KiB or one inline code value; round trip and exact decoded bytes |
| Explicit whole-file digest or byte count | `tools/artifact_inventory.py` plus hashlib/stat; SHA-256, SHA-1, SHA-512, MD5 or original file size |
| Total packets in one whole classic PCAP | `tools/pcap_summary.py`; filters, truncation, parser warnings and PCAPNG cannot yield a verified count |
| Final status of one saved HTTP response | `tools/http_response_inspect.py`; questions about individual redirects need another adapter |
| Explicit timestamp conversion | `tools/timestamp_convert.py`; one explicit epoch/unit and ISO UTC with six fractional digits |
| Image creation time, optionally rounded down to the minute | `tools/image_metadata.py`; original JPEG/TIFF/PNG EXIF dates, conflicts reported, no filesystem-time or timezone guesses |

Question shapes are deliberately narrow. A filtered count, derived value, multi-step decoding, ambiguous evidence set, unsupported metadata field or format-only match is **Inconclusive**. Available code is integrated through fixed adapters; the bot never turns question text, attachments or answers into shell commands, imports or executable code. No AI opinion is used as proof.

Enable optional **OpenAI assistance** in `/ws settings` after adding your
private API key. When a local check is inconclusive, the AI can select evidence
tools, explain findings and suggest an unverified candidate or next check.
Its assessment is distinguished from a local verified result; API/tool errors
never become incorrect answers. Read the [setup, data-sharing and usage-limit
details](../bots/skyline_archive/README.md#optional-openai-answer-assistance).

Each check runs in the configured Python interpreter in an isolated child process with JSON stdin and a stripped environment. Only one worker runs at a time. There is a 15-second wall timeout, 64 MiB per-file limit, cache hash validation and bounded output. On Linux/PebbleHost the worker also has 8 CPU seconds, 512 MiB address space, a 1 MiB file-write limit and 64 file descriptors. These are resource limits, not a general OS sandbox. Only fixed trusted repository code executes; adapters make no network calls. On Windows the wall/file/input limits remain but POSIX resource limits do not apply.

Results are **Verified correct**, **Verified incorrect**, **Inconclusive**, or **Verification error**, with method and concise evidence in the same thread. A tool failure is always an error, never an incorrect answer. Records include exact answer, submitting owner, timestamp, method, outcome and evidence in private SQLite; the parent displays the latest status. Interrupted jobs retain an unfinished/error record and can be retried. This does not submit answers, change platform completion state or establish Cyber Skyline acceptance.

## Delete Discord archives already exported to GitHub

Run `/ws cleanup preview` from the archive hub. With no filters it checks all known archive channels; optional `season`, `competition`, `category` and `difficulty` filters narrow the scope. The nested cleanup group shares `/ws` with survey and maintenance groups within Discord's 25-child limit. It uses the same authorized owners and configured server.

The paginated, private preview lists eligible channels, empty-after-cleanup categories and reasons for keeping other objects. It reads the configured GitHub branch at one immutable commit, validates the managed manifest, and compares every current rendered question's Git blob hash with both the manifest and actual repository tree. A local synced flag, similar filename or matching challenge title is insufficient. Missing questions, older content, manually changed files, incomplete trees and GitHub access failures block cleanup. Sanitized public prompt copies are what is verified; the original private inputs are not public backups.

Only recorded archive channels with their WS or legacy NCL topic identity and a verified bot post marker qualify. Old shared difficulty channels are checked against every associated challenge, across seasons and competitions. A mixed-scope channel stays intact. Unmapped channels and configured progress/notification/system destinations are kept. Categories are removed only when a fresh Discord inventory shows they are empty; retained or newly added children block category deletion.

To execute, choose **Delete listed archives…**, then type the exact displayed phrase containing the channel and category counts. The preview expires after ten minutes and cannot be reused. Confirmation rechecks GitHub and Discord and rejects any changed plan instead of adding new items. Each deletion checks that the GitHub head is still the verified commit. A GitHub branch and Discord cannot be updated atomically; subsequent edits to GitHub do not restore deleted Discord content.

**Deletion is permanent:** all messages, question threads, answers, discussions and Discord uploads in selected channels are removed. GitHub contains question prompts, not the Discord conversations or binary file backups. The command never writes to GitHub. Private source snapshots, cached evidence and verification records remain on the host. Deleted Discord links are cleared and the verified GitHub question links remain searchable by owners.

Deletion intent and per-challenge retirement are committed to SQLite before contacting Discord. Scheduled scans continue collecting/exporting questions but do not recreate retired Discord archives. Pending/failed cleanup attempts also remain retired until reviewed. An explicit manual scan or reorganization may rebuild prompts and question threads; it cannot recover deleted discussion. `/ws cleanup allow-recreate` clears retirement for the same optional filters, allowing future scheduled scans to rebuild them as well.

Cleanup shares the scan lock; manual/scheduled scans and setting changes cannot overlap it. `/ws stop` cancels remaining cleanup. Completed deletions cannot be undone. A restart reconciles uncertain results from a fresh channel inventory, clears stale links for missing channels, and never automatically retries a delete. Run a new preview to review/retry the remainder. The host's private `discord_cleanup` table records item IDs, owner, checked GitHub commit, state and sanitized failure information.

## Storage and migrations

The existing private `browser-state.json` and `survey-watches.json` remain in place. `archive.sqlite3` adds transactional tables for settings, source metadata, Discord mappings/posts, attachments, scan journals and verifications. SQLite schema v1 creates relational state; v2 adds/rebuilds FTS5; v3 adds complete snapshots, resumable scan jobs/items, historical question locations, supplemental evidence associations and separate AI assistance records. Schema v4 adds independent destination delivery fingerprints. Schema v5 adds Discord cleanup journals and scheduled-posting retirements. `archive.before-v5.sqlite3` is created before migrating an existing older database; old sync markers are retained but never guessed to represent success at both destinations. Existing question IDs, sync markers, files, verifications, settings and FTS rows are retained. A pre-upgrade database backup is created for an older nonzero schema version. A newer unsupported schema is refused rather than overwritten. The first upgrade from the original JSON-only bot creates SQLite without changing old files; `/ws maintenance reindex` imports its existing GitHub manifest.

Back up the entire private directory while the bot is stopped, including SQLite sidecars and evidence files. It must remain outside the Git checkout. Never publish the database, downloaded evidence, answers, session or environment file. The existing GitHub v2 manifest, redaction policy, collision handling and atomic/non-forced publication remain intact. Preserve that public manifest along with the private database; they track different destinations.

## Partial scans, event opening and health

`/ws failures` is an owner-only, private report of the latest saved scan with failures. It works while scanning, reads existing SQLite records without changing them, and survives restarts. **Previous**, **Next**, and **Refresh** browse each failed challenge with its event/category, saved reason, safe source link, scan start time and suggested next step. Reason counts distinguish interactive challenges, page/network errors and file/destination problems. Optional `scan_id` selects an older run; pagination stays on that run even if a newer scan starts. Up to three current attachment errors are shown for each challenge, excluding supplemental evidence. Known credentials, headers, embedded URLs and mentions are sanitized.

This is a view of currently failed items, not an immutable error history: retrying resets their state and successful retries remove them from the report. Older run-level/discovery errors may have no per-challenge record; the report links their progress message instead of inventing a reason. `/ws retry-failed` always targets the latest failed run. An interactive conversation requiring submitted replies remains unsupported by automatic retries.

Complete challenges can publish when another source page fails. Failed pages/publications remain in the durable queue, with an error reason, and are retried by `/ws retry-failed`. A network failure is separate from invalid login. Interactive chat challenges such as Launchpad reveal later questions only after submitted replies; the read-only scanner diagnoses these explicitly and never exports participant chat or submits replies. Other unrecognized layouts retain their extractor error. No incomplete challenge is marked synced.

An event with a rendered opening countdown displays **waiting for event**, reuses one waiting message and shows the next scheduled check. A scheduled non-preview scan attempts one owner notification when accessible challenges appear. Notification failure does not stop scanning; uncertain delivery is not repeatedly retried. Paused/checkpoint work holds scheduling until resume. Terminal elapsed time is frozen and ETA cleared; download/cache and upload/link counts are separate.

`/ws maintenance health` validates the source session, reads the configured GitHub branch, checks destination/server permissions and shows storage usage, last archive success and next schedule. It does not perform a test commit. `test_ai:true` makes one small API request, shares no question data and stores no verification; it counts against the daily request budget. A successful login health check clears a known authentication block.

## Supplemental evidence and AI assistance

In a question thread, use `/ws evidence file:<upload>` or `/ws evidence message_id:<your-message-id>`. With no arguments it chooses your latest attachment-bearing message within the last 100 messages. Message-history uploads require Message Content Intent; direct file input does not. Only your own uploads from that thread are accepted, up to ten per message. Cached files, hashes, submitting user, question/thread/message association and status persist privately. The source artifact and supplemental-file namespaces are separate; supplemental evidence is never posted to GitHub or shared with other questions.

Use `/ws hint` for a next investigative step or `/ws explain` for a solving approach without an answer. These use the configured AI switch, model, request budget and fixed tools; they never invoke the verification tool or update parent verification status. Reports are saved in the separate assistance table and posted in the same thread, explicitly as suggestions. As with verification, bounded excerpts are sent to OpenAI; images are inspected for metadata, not visual interpretation. Large files stay cached above Discord limits: file facts and the first 8 KiB of text/strings are supported; operations requiring a whole-file parser remain limited to 64 MiB. Full memory-image analysis is outside this 1 GiB host runtime.
