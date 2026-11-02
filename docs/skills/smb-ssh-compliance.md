# Skill: SMB discovery, SSH accounts, and compliance tools

Use this for a lab where a share exposes information and a scanner executes checks on another machine. Keep the scanner and target contexts explicit throughout.

## Establish what guest access actually permits

From the scanner:

```sh
smbclient -L //target -N
```

Wait for the share rows; a successful anonymous login followed by an interrupted header is not a completed listing. If `timeout` exists, an outer bound such as `timeout 30s smbclient -L //target -N` can prevent an indefinite wait. A timed-out result is incomplete. A message about unavailable SMB1 workgroup browsing after a valid listing does not by itself invalidate that listing.

Select the relevant disk share from actual output, then test access. These are templates, not literal ready-to-run commands:

```text
smbclient //target/DISCOVERED_SHARE -N -c 'ls'
smbclient //target/DISCOVERED_SHARE -N -c 'get OBSERVED_FILE'
```

Listing the server does not prove a particular share or file is readable. Download only the relevant challenge input and inspect its format. If it is Base64, decode it as data; encoding is not encryption. Preserve punctuation and exact bytes in any recovered credential. Keep the value private.

## Separate account discovery from privileges

Authenticate only with credentials established by the challenge evidence. Record the account that actually succeeded, not just the one named in a profile. SSH login proves authentication to that account; it does not prove file access or sudo permission.

On the target, inspect `id`, relevant home/configuration directories, ownership and modes, and account records. If appropriate, inspect `sudo -l` for the **current** account. `sudo -n` prevents an interactive password prompt; it does not bypass authentication or grant authorization. Password-required and policy-denied errors have different meanings.

An ordinary script being owned by root does not mean it executes as root. A root-only file needs an established privileged route, applicable ACL, or another actual access mechanism. Do not assume a service account has that route before inspecting its policy.

## Inspect the scanner instead of imagining its behavior

On the scanner, inspect local hidden files and the tool's help. Locate the executable with `command -v`. Read a text wrapper when permitted, and identify:

- How it parses a profile and which sections are required.
- Whether CLI credentials override profile credentials.
- Whether commands run locally or over SSH, and under which account.
- How it passes arguments, handles quoting, and reports stdout/stderr.
- Whether PASS means a compliance assertion succeeded or only that the command returned zero.

A wrapper around SSH runs with the remote login account's rights. Editing the profile's command cannot make an account acquire sudo rights that the server denies. A named service account without a known password is an unresolved authentication step, not an invitation to fill in a plausible password.

## Edit and verify a working profile

Copy the observed profile before editing. The following is **INI file content**, not a shell command:

```ini
[check]
command = COMMAND_CONFIRMED_BY_THE_HELPER_AND_ACCOUNT_POLICY
```

Replace the setting inside the working file using an editor or a deliberate file-writing command. Then read the file back. A commented instruction to edit it does nothing, and typing `command = ...` at a shell produces a parsing/command error.

If the target exposes a helper that maps check IDs to commands, inspect that mapping and the actual sudo policy. Permission to invoke a particular helper does not imply permission to invoke `cat` directly. Use the exact authorized executable and arguments after verifying the service account; do not invent the missing password or assume a broad sudo grant.

## Credential investigation without circular retries

Search readable, relevant configuration, backup files, and documented startup scripts on the **correct machine**. Prefer the paths revealed by account records, help, and source. Use `rg` where installed, otherwise a scoped `grep` or directory listing. Note inaccessible paths. A failed search on the scanner does not establish that the target contains no relevant configuration.

Separate SSH authentication rejection, a remote command's permission denial, sudo policy denial, and a malformed profile. Retrying the same unprivileged account through Hercules changes none of these permissions. Track what is unknown and the evidence needed for the next step.

See [the Hercules challenge investigation](../../challenges/hercules-compliance-audit/how-to-solve.md). References: [smbclient](https://www.samba.org/samba/docs/current/man-html/smbclient.1.html), [sudo manual](https://manpages.debian.org/bookworm/sudo/sudo.8.en.html), and [ConfigParser](https://docs.python.org/3/library/configparser.html).

## Repository helpers

Use [environment_report.py](../../tools/environment_report.py) to check scanner capabilities. This repository does not include a credential-guessing or privilege-granting tool; the helpers support the evidence and verification steps.
