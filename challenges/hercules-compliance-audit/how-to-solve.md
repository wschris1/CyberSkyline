# Hercules Compliance Audit: investigation guide

## Status and approach

This guide records verified investigation steps and an unfinished authentication/permission branch. The service-account password and protected file content were **not recovered in the recorded session**. Do not present the conditional steps below as a completed solve.

Read [SMB, SSH, and compliance tools](../../docs/skills/smb-ssh-compliance.md) and [terminal troubleshooting](../../docs/terminal-workflow.md). Keep a scanner-versus-target context table and a private question-evidence table.

## Establish the share and leaked account

1. On the scanner, list SMB shares without a supplied password:

   ```sh
   smbclient -L //target -N
   ```

   Allow the listing to finish. The observed anonymous login initially appeared before the actual share rows; interrupting at that point hid the useful output. A bounded retry was useful. The SMB1 workgroup message after a completed list did not prevent access to the selected share.

2. Test the observed disk share directly and list its files. Download the small relevant credentials file with `smbclient`'s `get` command. Decode its Base64 contents as data, preserving the exact account and password privately. Server listing, share access, and file retrieval are separate observations.

3. Use the recovered credentials to authenticate to the target. Record the actual login account and inspect `id`, its home directory, and relevant account records. Authentication succeeds independently of whether that account can read the protected file.

## Locate the local profile and inspect the tool

4. Return to the scanner before looking for the profile hidden on **your own machine**. Start with `ls -la ~`, then list the observed hidden directory. `find` was absent on the scanner in this session; a targeted `ls -laR` provided the needed listing.

5. Read the candidate profile. Identify its connection account, check identifier, description, and command. Confirm that the file is a check profile from its contents, not merely because its filename sounds like a token. Preserve its full observed path privately for the relevant question.

6. Inspect the scanner's help and locate its executable:

   ```sh
   hercules --help
   command -v hercules
   ```

   The local `man` alias only printed a message directing users to tool help; it did not provide a Hercules manual. Read the discovered wrapper source when accessible.

7. The observed wrapper parsed an INI profile, took CLI credentials in preference to profile credentials, and executed the profile command over SSH. Its PASS/FAIL label reflected the subprocess exit status. It did not itself grant elevated access. The profile specified a connection account but supplied no password; keep that missing credential explicitly unresolved.

## Investigate authorization

8. On the target, inspect the protected file's ownership and modes. In this session it was root-owned and not readable by the leaked account. The leaked account also received an explicit sudo-policy denial. Those findings rule out simply retrying a direct read with the same account through another client.

9. Inspect readable helper scripts and their check-ID mappings. A discovered helper implemented a content-reading check. Reading that source explains the operation, but does not establish that the current user can execute it with root privileges.

10. Investigate the intended service account through relevant readable configuration, documented startup files, backups, and other challenge evidence. Use observed paths and account records to narrow the search. Distinguish a local scanner search from a remote target search, and retain useful permission errors. No service-account password was established in the session documented here.

11. Once supported credentials are found, verify authentication as that account and inspect its actual allowed operations. A sudo permission for a specific helper is not a sudo permission for an arbitrary `cat` command. Construct the profile command from the observed policy and helper usage, not a guessed privilege grant.

12. Make a working copy of the profile, edit the actual INI entry, and read it back before running the scanner. A line beginning with `#` is a comment, and typing `command = ...` at the shell does not edit a profile. A literal password placeholder causes an authentication failure, not a meaningful test of the check.

## What would complete this investigation

Completion requires evidence for the service credential, that account's permitted way to run the check, and successful output from the intended protected file. Confirm which account executed the command and what the wrapper's status actually means. Keep all recovered values private and mark unresolved questions honestly until those observations exist.
