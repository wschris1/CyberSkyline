# Reusable investigation tools

These scripts use only the Python standard library and are intended for bounded, reproducible CTF work. Run them from the repository root with `python3 tools/<name>.py --help`. Keep original artifacts and all generated private output outside the Git checkout.

| Tool | Purpose | Safe default |
| --- | --- | --- |
| `environment_report.py` | Check which common analysis commands are installed | Never prints environment variables or credentials |
| `artifact_inventory.py` | Record file sizes, SHA-256 hashes, and signature-based types | Does not follow symlinks or read file contents into output |
| `safe_extract.py` | Validate, list, and optionally extract ZIP or tar archives | Rejects traversal, links, special files, duplicates, oversized archives, and nonempty destinations |
| `timestamp_convert.py` | Convert Unix and WebKit timestamps to UTC | `auto` shows interpretations without selecting one |
| `url_inventory.py` | Extract, count, and decompose HTTP(S) URLs | Redacts query values, user information, and fragments |
| `decode_value.py` | Perform one explicit hex, Base64, Base64url, URL-percent, or form-decoding step | Does not recursively guess transformations and reports a SHA-256 digest |
| `candidate_filter.py` | Stream an existing candidate list through character constraints | Does not generate candidates or test credentials/hashes |
| `new_challenge.py` | Create the required question and method-guide files | Refuses invalid slugs and existing destinations |

## Quick start

Check capabilities before choosing an approach:

```bash
python3 tools/environment_report.py
```

Inventory preserved artifacts using paths relative to their private working directory:

```bash
python3 tools/artifact_inventory.py \
  --relative-to /private/work/challenge \
  /private/work/challenge
```

Inspect an archive before extraction, then extract only into a new or empty directory:

```bash
python3 tools/safe_extract.py /private/work/input.zip
python3 tools/safe_extract.py /private/work/input.zip \
  --extract /private/work/extracted
```

Interpret a known timestamp format explicitly. Use `--format auto` only to compare hypotheses:

```bash
python3 tools/timestamp_convert.py --format unix-us 1700000000000000
```

Summarize URLs without printing tokens or query values:

```bash
python3 tools/url_inventory.py /private/work/browser-export.txt
```

Decode one known layer and preserve binary output separately:

```bash
python3 tools/decode_value.py base64 --input-file /private/work/value.txt \
  --output /private/work/decoded.bin
```

Filter a candidate set after all transformations have been applied:

```bash
python3 tools/candidate_filter.py /private/work/candidates.txt \
  --min-length 10 --uppercase 1 --special 1 --ascii-only \
  > /private/work/filtered.txt
```

Create a new public challenge skeleton:

```bash
python3 tools/new_challenge.py example-challenge "Example challenge"
```

## Interpretation limits

- Signature checks are a starting point, not complete format identification. Confirm important types with a second parser or the native application.
- Safe archive validation reduces common extraction risks; it does not establish that extracted content is trustworthy.
- Timestamp `auto` output is intentionally noncommittal. Choose an epoch and unit from the source schema, known events, or documentation.
- URL host output is not a registrable-domain calculation. Use a current public-suffix implementation when that distinction matters.
- URL decoding leaves `+` unchanged; use the separate `form` mode only for form-encoded data where `+` represents a space.
- Candidate filtering proves only that a string matches the requested syntactic constraints. It does not verify a password.
- Automated publication checks catch known patterns, not every possible answer. Always inspect the full staged diff manually.
