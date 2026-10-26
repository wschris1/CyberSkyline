# CyberSkyline CTF

This repository holds CTF challenge questions and guides for solving them. It does not hold flags, final answers, answer hashes, validation keys, or private scoring data.

## Start here

- [CTF playbook](docs/ctf-playbook.md): first checks, techniques by challenge type, independent verification, and publication review.
- [Investigation notes and handoff template](docs/investigation-notes-template.md): copy outside the repository to record evidence, failed approaches, checkpoints, and next steps.
- [Instructions for AI contributors](AGENTS.md): repository rules and expectations for future assistants.

## Challenge guides

| Challenge | Method |
| --- | --- |
| [Cybersecurity community](challenges/cybersecurity-community/question.md) | [Research workflow](challenges/cybersecurity-community/how-to-solve.md) |
| [Device default passwords](challenges/device-default-passwords/question.md) | [Identify the device and consult its documentation](challenges/device-default-passwords/how-to-solve.md) |
| [Water-damaged barcode](challenges/water-damaged-barcode/question.md) | [Decode visible bars and verify the institution](challenges/water-damaged-barcode/how-to-solve.md) |
| [Intercepted secure message](challenges/intercepted-secure-message/question.md) | [Decode phonetic words and dot groups](challenges/intercepted-secure-message/how-to-solve.md) |
| [Cooking With This XOR That](challenges/cooking-with-this-xor-that/question.md) | [Reverse several XOR feedback schemes](challenges/cooking-with-this-xor-that/how-to-solve.md) |
| [Archived internal memos](challenges/archived-internal-memos/question.md) | [Use known plaintext to test for keystream reuse](challenges/archived-internal-memos/how-to-solve.md) |
| [Scrambled Python code](challenges/scrambled-python-code/question.md) | [Inspect bytecode and invert its input check](challenges/scrambled-python-code/how-to-solve.md) |
| [Live relay cipher](challenges/live-relay-cipher/question.md) | [Recover generator state from predictable padding](challenges/live-relay-cipher/how-to-solve.md) |
| [Unauthorized network services](challenges/unauthorized-network-services/question.md) | [Correlate Zeek logs and assess exposed services](challenges/unauthorized-network-services/how-to-solve.md) |
| [Blurred messages](challenges/blurred-messages/question.md) | [Match fonts and recover text through pixel comparison](challenges/blurred-messages/how-to-solve.md) |
| [Cyber Command](challenges/cyber-command/question.md) | [Decrypt TLS and extract hashes; password recovery remains incomplete](challenges/cyber-command/how-to-solve.md) |
| [DMZ terminal](challenges/dmz-terminal/question.md) | [Fingerprint the protected service and validate an internal HTTP pivot](challenges/dmz-terminal/how-to-solve.md) |
| [Web security source review](challenges/web-security-source-review/question.md) | [Map source-controlled routes and verify each browser-facing weakness](challenges/web-security-source-review/how-to-solve.md) |
| [Scanner Unix socket](challenges/scanner-unix-socket/question.md) | [Correlate local listeners with the owning process and use the intended socket pivot](challenges/scanner-unix-socket/how-to-solve.md) |

## Challenge format

Each challenge has two required text files. If the image is part of the question, it may also have a `question.png`:

```text
challenges/<challenge-name>/
├── question.md       # The prompt and information given to players
├── how-to-solve.md   # The method and reasoning, without the final answer
└── question.png      # Optional image supplied with the prompt
```

Copy `challenges/_template` to start a challenge. Replace the bracketed guidance in both files. The solving guide can explain the tools, commands, and reasoning a player needs, but must stop before stating the final flag or answer. Keep challenge artifacts and private scoring material outside this repository; link to an externally hosted artifact in the question if one is needed.

## Investigation guides

- [Map itinerary](challenges/map-itinerary/how-to-solve.md)
- [Vessel tracking](challenges/vessel-tracking/how-to-solve.md)
- [Wordlist hashes](challenges/wordlist-hashes/how-to-solve.md)
- [Encrypted files](challenges/encrypted-files/how-to-solve.md)
- [Password hint sheet](challenges/password-hint-sheet/how-to-solve.md)
- [Encoded backup](challenges/encoded-backup/how-to-solve.md)
- [Nginx basic authentication](challenges/nginx-basic-auth/how-to-solve.md)

Upload new challenge images or plain-text inputs to `IMAGES/`. Supported image formats are PNG, JPEG, GIF, and WebP; text inputs use `.txt`. Move or copy an image into its challenge folder as `question.png` when adding the question and guide.

## Check before committing

Run `python3 .github/scripts/check_challenges.py`. The same check runs in GitHub Actions on pushes and pull requests. It requires both text files for every challenge, permits an optional question image plus supported images and text inputs in `IMAGES/`, rejects other challenge files, and catches common flag and answer leaks. Review the text and images yourself too: an automated check cannot recognize every possible answer.
