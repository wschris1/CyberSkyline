# Terminal workflow: hosts, permissions, and reliable commands

## 1. Establish the task and the machine

Copy the question exactly into private notes. Record whether it requests a complete message, product version, protocol banner, hostname, path, count, date, or token. Keep requested case, trailing slashes, units, rounding, and timezone explicit. Save the challenge's scope and any restrictions on automation.

Identify each execution surface separately. In a multi-host exercise, use a table like this privately:

| Surface | Account | Purpose | Evidence paths |
| --- | --- | --- | --- |
| Assistant workspace | Observed local user | Analysis and documentation | Local artifact copies |
| Scanner terminal | Observed scanner user | Client tools and local profiles | Paths observed on scanner |
| Remote target | Authenticated remote user | Target configuration and services | Paths observed on target |

At a shell, short context checks are:

```sh
hostname
id
pwd
```

If one is missing, use the available checks and the prompt as a clue. `exit` from SSH returns to the previous machine. A noninteractive `ssh USER@target 'command'` runs the quoted command remotely and then returns locally. Absolute paths and `~` are meaningful only in the context where they expand. Preserve that context when recording evidence.

## 2. Establish local capabilities

Keep original artifacts unchanged and work on copies. Record filenames, byte lengths, and SHA-256 checksums when available. Binary inputs belong in files, not clipboard transcripts. Capture stdout, stderr, and exit status separately when diagnosing a tool; warnings on stderr do not necessarily mean failure.

Check only the tools needed for the next step with `command -v`. A missing `find` does not require package installation: a small `ls -laR` over a known directory may be enough. Use `rg --files --hidden DIRECTORY` when installed to list files, and `rg -n -i PATTERN DIRECTORY` for text. Scope searches before increasing depth; record permission errors instead of treating them as proof of absence.

On a minimal shell, consult `TOOL --help`; a shell alias can replace `man` or another familiar command. Read `type TOOL` or `command -v TOOL` before trusting a wrapper. A program installed on the scanner may be absent on the target.

## 3. Triage, then test a hypothesis

Choose the playbook from [the skill index](README.md) and follow the [AI workflow](ai-workflow.md) for the wider investigation. Begin with cheap discriminators: file signatures, table schemas, open ports, header fields, or configuration sections. Avoid an all-ports exhaustive version scan when a short port inventory and one protocol request will answer the question.

Maintain a private attempt log:

| Hypothesis | Test and host | Actual result | Interpretation | Next check |
| --- | --- | --- | --- | --- |
| A listed share permits guest reads | List that share without a password | Record exact output | Listing the server alone is insufficient | Read only the relevant file |
| A wrapper can read a protected file | Inspect wrapper and effective account | Record invocation and status | Wrappers inherit the remote account's rights | Check that account's policy |

Ask what would falsify the hypothesis. A plausible prefix is weak evidence; a complete hash match, parsed protocol response, byte-for-byte round trip, or independent source is stronger. A timeout means the test was incomplete, not that the service or file is absent.

If two attempts yield the same underlying failure, stop repeating them. Change the account, input, format assumption, or test **only when evidence supports the change**. Keep the old result so a later AI does not restart a dead end. Time estimates from scanners are not deadlines or guarantees.

## 4. Classify errors before changing the command

| Observation | Layer | Useful next action |
| --- | --- | --- |
| Duplicated input, `^[[200~`, or an unfinished quote | Terminal input | Cancel the partial line, get a fresh prompt, paste one command |
| `command not found` | Local shell/tool availability | Check the host, spelling, alias, and installed alternatives |
| Profile cannot be loaded | Local file/configuration | Verify path, existence, sections, and actual saved content |
| Name cannot resolve or connection refused | Network/service | Confirm instance, hostname, scope, and listening port |
| SSH rejects credentials before the command runs | Authentication | Verify username and exact known password; unresolved placeholders are not credentials |
| `cat: ... Permission denied` after login | Filesystem authorization | Inspect identity, ownership, modes, and relevant ACL/policy |
| Account may not run sudo | Sudo authorization | Record the denial; the same account through another wrapper still has that policy |
| Program prints PASS/FAIL | Application result | Read the source of that status and actual output; command exit success may be all it means |
| Platform rejects an otherwise verified value | Submission format or hypothesis | Recheck complete versus partial value, case, units, whitespace, and source |

## 5. Make copy-and-paste instructions reliable

State the machine outside the code block. Exclude prompts and copied output. Give one command per step when the user requests guided work. If input is visibly corrupted, clear it with Ctrl+C before a retry; on a confirmed Bash prompt, Ctrl+U clears an unexecuted line. Do not keep appending text to an incomplete paste.

Label configuration blocks as `ini`, `yaml`, or the correct format. `command = ...` is an INI entry, while `# edit the file` is only a shell comment. Neither changes a file when pasted as shell instructions. After a real edit, read the saved file and check the exact command the tool will execute. Use a working copy so the original evidence stays intact.

Do not put unresolved angle-bracket placeholders in a command presented as ready to run. Shell redirection can interpret unquoted angle brackets, and a quoted placeholder simply supplies the wrong literal value. When a known password must be entered, use the program's prompt when possible; do not copy real credentials into public documentation.

## 6. Verify, report, and preserve continuity

Use [the checklist](verification-checklist.md). Distinguish a candidate, a verified observation, and a platform-accepted result. Do not claim acceptance without feedback. Preserve the exact raw value privately before interpreting it; for example, a software version and an SSH protocol banner are related but different strings.

Before a one-shot instance ends, retain authorized evidence and unresolved notes privately. Never claim the remaining questions are solved when only the first few have evidence. Leave a concise handoff with the current prompt, host/account, known files, last successful command, rejected approaches, and next test. Publish only the method after reviewing it for answers and secrets.
