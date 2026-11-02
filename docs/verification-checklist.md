# Checks before reporting or publishing

## Scope and session

- [ ] The command applies to the current challenge instance and authorized host, port, or artifact.
- [ ] The current machine, account, working directory, and shell are known.
- [ ] Paths and tools have been checked on that machine; an old session's IP or permissions were not assumed.
- [ ] Required evidence has been retained privately before an instance can disappear.

## Evidence and interpretation

- [ ] Every reported value has an exact source: response line, file/path, packet/stream, log row, database query, or cited record.
- [ ] A port's conventional label has not been treated as confirmed protocol detection.
- [ ] The full banner is preserved; protocol prefix, software version, and distribution suffix are distinguished.
- [ ] A service-advertised hostname is not confused with a container's reverse-DNS name.
- [ ] Anonymous SMB authentication, server share listing, share access, and file readability were treated as separate checks.
- [ ] Credentials belong to the specified account and service. Encoding was decoded without silently changing bytes.
- [ ] Authentication failure is distinguished from file permissions, sudo denial, and malformed local configuration.
- [ ] Counted objects match the question: packets, streams, requests, unique devices, hosts, visits, files, or matching strings.
- [ ] Timestamps have the correct epoch, units, timezone, and requested rounding.
- [ ] A cryptographic result passes a full digest, MAC, authenticated extraction, or equivalent check; a short verifier or recognizable text alone is insufficient.
- [ ] Byte order, bit order, offsets, padding, character encoding, and delimiters were made explicit where relevant.
- [ ] Parser acceptance, syntactic validity, or a printed PASS has not been overstated as proof of the final answer.

## Answer readiness gate

Use this gate **for each question immediately before giving a value to the user**. Keep the working record private, especially when it contains a flag, credential, hash, or instance-specific URL.

| Field | Record privately |
| --- | --- |
| Question and format | Exact wording, exclusions, requested units, date context, and submission syntax |
| Candidate and source | Proposed value plus a precise locator in the original artifact, response, packet, row, or authoritative record |
| Reproduction | Transformations, tool/version, parameters, and a rerun from unchanged input |
| Independent check | A different check against the original evidence that does not reuse the candidate's assumption |
| Conflicts and limits | Competing candidates, missing records, parser errors, truncation, search coverage, or stale sources |
| Platform feedback | Accepted, rejected, or not submitted; keep this separate from technical verification |

Apply one of these outcomes:

- **Verified:** The original evidence supports the value, the reproduction and meaningful independent check agree, the exact requested format is satisfied, and no material contradiction remains. Give the answer with a short evidence basis.
- **Candidate:** The value is plausible but a required check or source is missing. Label it as unverified and state the specific check needed. Do not present it as a final answer.
- **Unresolved:** The evidence cannot support a defensible value. State what is missing and the next bounded step rather than guessing.

An independent check must test a different failure mode. Repeating the same OCR text in two tools, copying a prior assistant's answer, or reformatting the same search snippet does not count. If a second check is impossible, say so and limit the claim. Platform acceptance is useful feedback, but do not claim it happened without seeing it.

## Final response

- [ ] The exact requested scope of each value is satisfied: full sentence versus token, hostname versus URL, directory versus file, and version versus banner.
- [ ] Capitalization, punctuation, spaces, leading zeroes, trailing slash, and formatting match the evidence and prompt.
- [ ] Unknowns and inferences are labeled; no missing password, account, or flag was invented.
- [ ] Independent verification agrees, and any conflicts are explained.
- [ ] No answer was submitted or challenge completed without the user's authorization.

## Public repository update

- [ ] Only questions, methods, reusable skills, and permitted question inputs are included.
- [ ] Recovered outputs, live credentials, private keys, key logs, session tokens, scoring data, and answer-bearing images remain outside the commit.
- [ ] Filenames, Markdown, images, code samples, commit messages, and PR text have all been reviewed for leaks.
- [ ] Each added challenge has the required two files; links point to files that actually exist.
- [ ] The automated checks pass, and their limits are understood: they detect selected patterns, not every possible secret or answer.
- [ ] The published commit and destination branch have been verified against the intended changes.
