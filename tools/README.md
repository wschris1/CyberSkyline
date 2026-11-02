# Investigation toolkit

[Home](../README.md) · [Skill playbooks](../docs/README.md) · [Verification checklist](../docs/verification-checklist.md)

**18 command-line helpers. Python 3.10+. Standard library only.** Run from the repository root. These helpers operate on local files; they do not scan hosts, log into accounts, submit answers, or install other tools. `environment_report.py` can invoke installed programs to read their versions; `--no-version` only checks paths.

Keep original artifacts and generated evidence outside the Git checkout. Use copies for analysis. Each helper supports `--help`; select one that resolves a specific question rather than running the entire catalog blindly.

## Find the right tool

| Task | Tool | Output and limits |
| --- | --- | --- |
| Check local capabilities | [environment_report.py](environment_report.py) | Paths and optional version lines; no environment variables |
| Preserve an artifact inventory | [artifact_inventory.py](artifact_inventory.py) | Sizes, SHA-256, header signatures; TSV or JSON |
| List or extract an archive | [safe_extract.py](safe_extract.py) | ZIP/tar validation; traversal, links, special files, duplicate paths, size limits, and destination checks |
| Locate readable strings | [strings_extract.py](strings_extract.py) | JSON with byte offsets and encodings; printable ASCII, including ASCII-range UTF-16LE/BE |
| Inspect exact bytes | [hex_view.py](hex_view.py) | Hex/ASCII rows with absolute offsets; 256 bytes by default |
| Compare two artifacts | [binary_diff.py](binary_diff.py) | Offset-aligned differing ranges and totals, including unequal tails |
| Measure byte distributions | [entropy_scan.py](entropy_scan.py) | Shannon entropy per window, in bits per byte; no encryption classification |
| Find embedded magic bytes | [signature_scan.py](signature_scan.py) | Candidate offsets only; does not carve or validate formats |
| Decode a known representation | [decode_value.py](decode_value.py) | Hex, Base64, Base64url, URL, or form decoding; one step, SHA-256 and round-trip information |
| Apply a known XOR key | [xor_bytes.py](xor_bytes.py) | Repeating-key XOR to a **new** file; no key search or overwrite |
| Filter existing candidates | [candidate_filter.py](candidate_filter.py) | Exact character-count and length constraints; no credential testing |
| Inspect an SSH public key | [ssh_public_key.py](ssh_public_key.py) | Plain RSA/Ed25519 structure and SHA-256 fingerprint; comments omitted |
| Understand JSON Lines logs | [jsonl_summary.py](jsonl_summary.py) | Schema/type counts; explicit `--field` enables scalar-value counts |
| Inspect a copied SQLite database | [sqlite_inspect.py](sqlite_inspect.py) | Schema names, table preview, or bounded SELECT; read-only connection |
| Inspect a saved HTTP response | [http_response_inspect.py](http_response_inspect.py) | HTTP/1.x status, header names, framing warnings and trailing-byte digest; values opt-in |
| Summarize URLs | [url_inventory.py](url_inventory.py) | Hosts, paths, query keys, counts; query values, user information and fragments hidden by default |
| Compare timestamp interpretations | [timestamp_convert.py](timestamp_convert.py) | Unix seconds/ms/us/ns and WebKit microseconds to UTC |
| Start a public guide | [new_challenge.py](new_challenge.py) | Required question/method files; refuses an existing destination |

## Setup and preservation

```bash
python3 tools/environment_report.py --no-version
python3 tools/artifact_inventory.py --json --relative-to /private/work /private/work/input
python3 tools/safe_extract.py /private/work/input.zip
python3 tools/safe_extract.py /private/work/input.zip --extract /private/work/extracted
```

Archive extraction requires a new or empty destination. Archive checks reduce common extraction risks; they do not make extracted content trustworthy. Inventory signatures are hints to confirm with a format-aware parser.

## Binary triage

```bash
python3 tools/strings_extract.py /private/work/sample.bin --minimum 6 --limit 100
python3 tools/hex_view.py /private/work/sample.bin --offset 0x100 --length 128
python3 tools/binary_diff.py /private/work/original.bin /private/work/working.bin
python3 tools/entropy_scan.py /private/work/sample.bin --window 4096
python3 tools/signature_scan.py /private/work/sample.bin --limit 50
```

- Offsets are **zero-based bytes**, not characters. Diff range ends are exclusive. A hex-view offset exactly at EOF produces no rows; an offset beyond EOF is rejected.
- String extraction reports printable ASCII only, including that subset encoded as UTF-16. It does not reconstruct arbitrary Unicode. UTF-16 matches may start at odd offsets or overlap another encoding; inspect neighboring bytes before interpreting a match.
- Binary comparison aligns the same offsets. An insertion shifts later bytes; the tool does not resynchronize or compute an edit script. Previews show at most 16 bytes per differing range.
- High entropy can arise from compression, encryption, or other byte distributions. Short windows are biased; the final partial window reports its actual size.
- Short file signatures can occur by chance. A signature hit is not proof of an embedded, extractable file. `--list-signatures` shows the finite signature set.

## Encoding and key checks

```bash
python3 tools/decode_value.py base64 --input-file /private/work/value.txt --output /private/work/decoded.bin
python3 tools/xor_bytes.py /private/work/cipher.bin --key-file /private/work/key.bin --output /private/work/plain.bin
python3 tools/candidate_filter.py /private/work/candidates.txt --min-length 10 --uppercase 1 --special 1 --ascii-only --count-only
python3 tools/ssh_public_key.py /private/work/candidate.pub
```

`xor_bytes.py` takes raw key-file bytes, including any newline. `--key-offset` selects the starting phase in the repeating key; it does not skip input bytes. Apply the same key and phase to reverse the transform, then validate against the original challenge logic. For nonsensitive examples, `--key-hex 20` supplies one hexadecimal byte.

URL decoding leaves `+` unchanged; `form` mode treats it as a space. A decode round trip verifies representation, not meaning. Candidate filtering verifies syntax only. The SSH helper checks plain RSA and Ed25519 structures; it does not validate ownership, signatures, curve membership, or RSA strength. Certificates, private keys, ECDSA keys, and `authorized_keys` option prefixes are outside its scope. Compare a fingerprint with `ssh-keygen -lf FILE -E sha256` when available.

## Logs, databases, and time

```bash
python3 tools/jsonl_summary.py /private/work/events.jsonl
python3 tools/jsonl_summary.py /private/work/events.jsonl --field 'id.orig_h'
python3 tools/sqlite_inspect.py /private/work/history.sqlite
python3 tools/sqlite_inspect.py /private/work/history.sqlite --table visits --limit 20
python3 tools/sqlite_inspect.py /private/work/history.sqlite --query 'SELECT COUNT(*) AS visits FROM visits'
python3 tools/timestamp_convert.py --format unix-us 1700000000000000
```

JSONL schema mode omits record values. `--field` uses a **literal top-level key** (dots are not a nested-path syntax) and deliberately prints values. Null, missing, and nonscalar values remain distinct. Blank and malformed lines are counted separately; duplicate keys, invalid UTF-8, non-finite numbers and numbers outside finite float range are reported as invalid. Counters cover only the scanned prefix if `truncated` is true. Distinct keys/values and line sizes have explicit limits.

Preserve SQLite WAL/journal sidecars with a coherent working copy. The helper uses `mode=ro` and query-only mode; it refuses writes, ATTACH, PRAGMA statements, and extension loading. It defaults to schema names rather than dumping records. SELECT output is capped, BLOBs become length/digest summaries, and long text is previewed. A VM-instruction budget interrupts expensive queries, but is **not a complete CPU or memory sandbox**. Python 3.11+ additionally supplies SQLite length limits. Read-only SQLite access can still need shared-memory sidecars, so analyze a private copy. Missing or inconsistent sidecars can hide recent evidence.

Timestamp `auto` displays possible interpretations without choosing one. Select epoch and units from the source schema or known events; output is UTC at microsecond precision, so nanosecond input loses finer precision.

## Saved HTTP and URL evidence

```bash
python3 tools/http_response_inspect.py /private/work/response.bin
python3 tools/http_response_inspect.py /private/work/response.bin --show-values
python3 tools/url_inventory.py /private/work/browser-export.txt --hosts-only
```

The HTTP helper reads a **saved HTTP/1.0 or HTTP/1.1 response**, with optional preceding informational responses. It preserves duplicate header entries and hides every header value by default. Use `--show-values` privately to inspect custom headers, cookies, and redirects. Use `--request-method HEAD` or `CONNECT` when applicable; `--headers-only` marks a deliberately body-free capture. It reports conflicting lengths and transfer-encoding ambiguity, and rejects obsolete folded or malformed headers.

It does not fetch URLs, follow redirects, decode chunked bodies, decompress content, parse HTTP/2 frames, or split concatenated final responses. The reported digest covers the raw bytes after the final header block. A framing warning requires inspection, not an automatic exploit conclusion. URL host output is not a registrable-domain calculation; paths and hostnames can themselves contain private evidence even when query values are redacted.

## Limits and exit codes

The new in-memory binary/HTTP helpers default to **32 MiB per input**, adjustable with `--max-bytes`. They reject symbolic links and non-regular inputs. Hex view reads only the requested range (up to 1 MiB). SSH public-key input is capped at 64 KiB. JSONL defaults to 100,000 lines, 1 MiB per line, and 1,000 distinct keys/values. Archive, SQLite, and older helpers have their own limits; consult `--help`.

Most helpers return 0 on success and nonzero on failure. Two have comparison/data-quality status codes:

| Tool | 0 | 1 | 2 |
| --- | --- | --- | --- |
| `binary_diff.py` | Identical bytes | Differences found | Input/usage error |
| `jsonl_summary.py` | Scanned records parsed | Invalid records counted | Input/usage/limit error |

Successful execution can still produce `truncated: true`; check the output before claiming full coverage. These are investigation aids for an isolated analysis environment, not hardened parsers for arbitrary adversarial files. None automatically verifies a CTF response.

## External tools to reach for next

These are optional tools to check locally, not bundled dependencies. Use the installed version's help and the [matching playbook](../docs/README.md).

| Need | Examples | Double-check |
| --- | --- | --- |
| Live service identification | Nmap, Netcat, curl, smbclient, OpenSSH, dig | Authorized host, protocol response, timeout, account and execution machine |
| Packet reassembly and TLS | Wireshark/TShark, tcpdump | Direction, stream boundaries, key-log match and missing packets |
| Formats, metadata, archives | file, ExifTool, 7-Zip, binwalk | Original bytes, archive paths and actual format validation |
| Images, barcodes, media | ImageMagick, zbarimg, FFmpeg | Native pixels/channels and full reconstruction |
| Structured data and search | jq, SQLite, ripgrep, YARA | Schema, literal versus regex search, row/count unit |
| Cryptography and candidates | OpenSSL, John the Ripper, Hashcat | Exact algorithm, salts/rounds, bounded search and full verification |
| Executable analysis | readelf, objdump, GDB | Architecture, runtime version, signedness and isolated execution |

## Add a tool or guide

Keep helpers focused, document inputs and limits, preserve originals, and add synthetic tests for meaningful edge cases. Run:

```bash
python3 tools/new_challenge.py example-challenge "Example challenge" --dry-run
python3 -m unittest discover -s tests -v
python3 .github/scripts/check_challenges.py
```

Primary format references: [Python SQLite](https://docs.python.org/3/library/sqlite3.html), [HTTP/1.1 framing](https://www.rfc-editor.org/rfc/rfc9112.html), [SSH transport key encoding](https://www.rfc-editor.org/rfc/rfc4253.html), and [Ed25519 SSH keys](https://www.rfc-editor.org/rfc/rfc8709.html).
