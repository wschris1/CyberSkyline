# CTF skills and AI handoff guide

Start with [AGENTS.md](../AGENTS.md) and [the AI investigation workflow](ai-workflow.md). For live terminal work, also read [hosts, permissions, and reliable commands](terminal-workflow.md). These playbooks are repository reference material for both humans and AI assistants; they are not automatically installed plugins. Ask a future assistant to read the repository instructions and the matching playbook before giving commands.

[Home](../README.md) · [20-tool catalog](../tools/README.md) · [All challenge guides](challenges.md) · [General CTF playbook](ctf-playbook.md)

| Situation | Read | Essential double-check |
| --- | --- | --- |
| A live host exposes unknown services | [Service enumeration](skills/service-enumeration.md) | Port label versus actual protocol; full raw banner versus product version |
| SMB leaks, SSH accounts, or a compliance wrapper | [SMB, SSH, and permissions](skills/smb-ssh-compliance.md) | Correct host, effective account, profile contents, and allowed sudo command |
| PCAP, TLS secrets, logs, or browser history | [Packet and log forensics](skills/packet-log-forensics.md) | Reassembly, distinct-count unit, time units, and complete records |
| Encodings, hashes, passwords, or cryptography | [Encoding, crypto, and password recovery](skills/encoding-crypto-passwords.md) | Bytes, algorithm parameters, exact constraints, and full verification |
| Images, archives, hidden data, or executables | [Files, images, and reverse engineering](skills/files-images-reversing.md) | Original artifact, format, extraction order, and independent validation |
| An authenticated web-app challenge | [Web-app CTF investigation](skills/web-app-testing.md) | Role and session context, controlled boundary tests, and verified effects |
| Web requests, historical facts, locations, or identities | [Web and OSINT](skills/web-osint.md) | Raw request, permitted scope, date, and authoritative corroboration |

Use the [verification checklist](verification-checklist.md) before reporting a result. Copy the [session template](investigation-notes-template.md) into a **private location outside this public repository** to resume work without repeating unsuccessful attempts.

The [service-enumeration challenge](../challenges/service-enumeration/how-to-solve.md) and [Hercules audit challenge](../challenges/hercules-compliance-audit/how-to-solve.md) document lessons from terminal-guided investigations. The latter preserves the unresolved authentication and permission questions rather than claiming a completed solve.

## How to use a command example

`target` refers only to the hostname explicitly supplied by the active challenge. Other names in uppercase are placeholders unless the text says otherwise. Set them from current evidence before use. Examples are selective investigation steps, not a script to run wholesale. Check local `--help` when a flag differs on the installed version. Tool names mentioned here are options, not a requirement to install everything.

Public documentation describes methods. Keep raw captures, passwords, candidate results, key logs, and answer-bearing screenshots in the private workspace. If you cannot edit this repository, use the [contribution handoff for any AI](contribution-handoff.md).
