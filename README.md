# CyberSkyline CTF

This repository holds CTF challenge questions and guides for solving them. It does not hold flags, final answers, answer hashes, validation keys, or private scoring data.

## Start here

- [CTF playbook](docs/ctf-playbook.md): first checks, techniques by challenge type, independent verification, and publication review.
- [AI contributor workflow](docs/ai-workflow.md): task scoping, evidence labels, bounded automation, handoff, and answer-free publication.
- [Investigation notes and handoff template](docs/investigation-notes-template.md): copy outside the repository to record evidence, failed approaches, checkpoints, and next steps.
- [Reusable investigation tools](tools/README.md): dependency-free helpers for artifact inventory, safe extraction, timestamps, URLs, decoding, candidate filtering, and challenge scaffolding.
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
| [Cyber Command: admin flag](challenges/cyber-command-admin-flag/question.md) | [Chain a redirect, dangling markup, framing, and CSRF](challenges/cyber-command-admin-flag/how-to-solve.md) |

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

## Reusable tools

The `tools/` directory contains small Python utilities designed for minimal analysis environments. They use only the standard library, expose `--help`, and default to preserving evidence or redacting sensitive values. Start by checking the environment and inventorying private artifacts:

```bash
python3 tools/environment_report.py
python3 tools/artifact_inventory.py --json /private/path/to/artifacts
```

See the [tool catalog and recipes](tools/README.md) for safe archive extraction, timestamp conversion, URL triage, explicit decoding, candidate filtering, and new-challenge creation. Keep all artifact paths and outputs outside this repository.

Upload new challenge images or plain-text inputs to `IMAGES/`. Supported image formats are PNG, JPEG, GIF, and WebP; text inputs use `.txt`. Move or copy an image into its challenge folder as `question.png` when adding the question and guide.

## Check before committing

Run both validation commands:

```bash
python3 .github/scripts/check_challenges.py
python3 -m unittest discover -s tests -v
```

The same checks run in GitHub Actions on pushes and pull requests. The content check requires both text files for every challenge, permits an optional question image plus supported images and text inputs in `IMAGES/`, rejects other challenge files, and catches common flag and answer leaks. Review the text, commands, URLs, and images yourself too: an automated check cannot recognize every possible answer.
