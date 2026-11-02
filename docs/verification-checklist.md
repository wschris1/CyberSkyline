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
