# CyberSkyline CTF

This repository holds CTF challenge questions and guides for solving them. It does not hold flags, final answers, answer hashes, validation keys, or private scoring data.

## Challenge format

Each challenge has two required text files. If the image is part of the question, it may also have a `question.png`:

```text
challenges/<challenge-name>/
├── question.md       # The prompt and information given to players
├── how-to-solve.md   # The method and reasoning, without the final answer
└── question.png      # Optional image supplied with the prompt
```

Copy `challenges/_template` to start a challenge. Replace the bracketed guidance in both files. The solving guide can explain the tools, commands, and reasoning a player needs, but must stop before stating the final flag or answer. Keep challenge artifacts and private scoring material outside this repository; link to an externally hosted artifact in the question if one is needed.

## Check before committing

Run `python3 .github/scripts/check_challenges.py`. The same check runs in GitHub Actions on pushes and pull requests. It requires both text files for every challenge, permits an optional question image, rejects other challenge files, and catches common flag and answer leaks. Review the text and images yourself too: an automated check cannot recognize every possible answer.
