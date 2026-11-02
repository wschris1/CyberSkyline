# Skill: packet captures, logs, and timelines

Use original captures and logs, preserve a checksum, and work from copies in a private workspace. Record the capture's start/end, timestamp basis, packet loss or truncation, and which evidence source answers each question.

## Network captures

With an existing local capture and TShark installed, start with summaries:

```sh
tshark -r capture.pcap -q -z io,phs
tshark -r capture.pcap -q -z conv,tcp
```

Identify endpoints and the relevant application before narrowing a display filter. `-Y` uses Wireshark display-filter syntax; live-capture `-f` uses a different filter language. Preserve frame numbers and stream IDs so each finding is reproducible.

Count the entity in the question. Packets, SYN attempts, retransmissions, TCP streams, HTTP requests, unique destination addresses, and physical devices are different quantities. A MAC address is useful where captured at the appropriate link, but it does not identify a remote internet endpoint across routed links. Correlate DHCP, DNS, mDNS, application traffic, and timestamps when identifying a device.

Use stream reassembly or protocol export for application data. A TCP read boundary is not a message boundary. Handle sequence, framing, lengths, retransmissions, missing segments, compression, and content encodings before interpreting bytes. Inspect both directions; an authentication request and its response must belong to the same exchange.

## TLS and authentication captures

If the challenge supplies a TLS key log, apply it to the matching capture. For example:

```sh
tshark -r capture.pcap -o tls.keylog_file:session.keys -Y http -V
```

This example selects decoded HTTP/1.x; absence of output is not proof that TLS decryption failed. The application may be HTTP/2 or another protocol. Confirm the TLS sessions, matching secrets, decoded application records, and appropriate dissector. Do not assume a server private key can decrypt every modern TLS exchange.

Inspect any provided application source before cracking a backend authentication exchange. Determine whether the captured value is a password, stored hash, challenge-response proof, salt, nonce, or key-derivation result. Reproduce the exact protocol operation and validate it against more than one captured field where possible. Never publish supplied key logs or recovered authentication material here.

## Logs and databases

Keep raw requests beside decoded copies. Decode deliberately and track each layer; double-decoding changes meaning. Use status, byte count, body evidence, and chronology to distinguish attempted access from successful retrieval. A `200` status alone does not prove the requested secret was returned.

For SQLite, preserve the database and relevant WAL/SHM sidecars as one acquisition. Analyze a copy and inspect schemas before writing queries. Read-only connections are preferable where supported. Firefox visit timestamps use microseconds since the Unix epoch; other applications may use a different epoch or scale. Do not apply one conversion globally based on a similar column name.

Calculate elapsed time from raw numeric values before rounding. Declare UTC or the requested timezone. Count visits with visit records, unique URLs with URL records, and registrable domains with public-suffix-aware logic. These are not interchangeable totals.

## Validation

Reproduce a claimed count with an explicit filter/grouping rule and inspect several included and excluded records. Reconcile the first and last rows with the computed interval. Confirm that a result uses the relevant device/session/date and has not mixed unrelated traffic.

Related guides: [conference capture](../../challenges/conference-network-capture/how-to-solve.md), [browser history](../../challenges/browser-history-investigation/how-to-solve.md), [web access logs](../../challenges/public-wordpress-log/how-to-solve.md), [product leak](../../challenges/choclympic-leak/how-to-solve.md), and [framed binary traffic](../../challenges/live-relay-cipher/how-to-solve.md).

References: [TShark manual](https://www.wireshark.org/docs/man-pages/tshark.html), [Wireshark TLS](https://wiki.wireshark.org/TLS), [Python SQLite access](https://docs.python.org/3/library/sqlite3.html), and [SQLite date functions](https://www.sqlite.org/lang_datefunc.html).

## Repository helpers

Use the [JSONL, SQLite, and timestamp recipes](../../tools/README.md#logs-databases-and-time) for schema discovery and bounded queries. Read truncation and invalid-record counts before interpreting totals.
