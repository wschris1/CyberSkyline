# Cyber Command: how to solve

## Progress reached

The capture was decrypted and five users' password hashes were extracted. Dictionary and targeted mutation searches produced no verified password matches. The decryption and extraction below succeeded; the cracking workflow records the attempted approach and what remains to be done.

Keep the capture, TLS secrets, decrypted response, extracted hashes, candidate lists, and cracking output in a private working directory outside this repository.

## Inspect and decrypt the capture

1. Identify the capture format from its file signature. Despite its extension, the supplied file is PCAPNG. Inspect its interface and packet blocks, then identify the TCP stream containing the backend TLS connection.
2. Load the capture and supplied key log in Wireshark. Set **Preferences → Protocols → TLS → (Pre)-Master-Secret log filename** to the key-log path, then inspect decrypted application data. A normal TShark installation can perform the same decryption:

   ```bash
   tshark -r traffic.pcap -o tls.keylog_file:sslkeylog.txt -Y http
   ```

   Wireshark/TShark is the convenient reproduction path. Those tools were unavailable in the analysis environment, so a Python implementation was used instead.
3. For that fallback, parse PCAPNG Ethernet/IP/TCP records and reassemble each direction by TCP sequence number. Handle retransmissions and detect gaps before parsing TLS records. Check the TLS ClientHello random against the key-log entries.
4. Read the negotiated cipher suite. This capture uses TLS 1.3 with AES-256-GCM and SHA-384. The key log supplies directional handshake and application traffic secrets.
5. Use TLS 1.3 HKDF-Expand-Label with SHA-384 and the `tls13 key` and `tls13 iv` labels to derive the 32-byte AES key and 12-byte IV for each secret. The record nonce is the IV XOR the padded record sequence number; the five-byte TLS record header is authenticated additional data.
6. Maintain separate counters for each direction and traffic-key epoch. Authenticate every record with AES-GCM, then remove inner padding and read the inner content type. Application-key records may still carry handshake messages such as session tickets; retain only application content when reconstructing HTTP.

Successful authentication of the decrypted records confirms that the key derivation and record boundaries are consistent. See [RFC 8446](https://www.rfc-editor.org/rfc/rfc8446) for the TLS 1.3 record and key-schedule details.

## Extract the backend data

1. Follow the decrypted HTTP stream. It contains a request to a debugging users endpoint and a successful JSON response.
2. Parse the response body as JSON and inspect its user-to-hash mapping. Preserve the association with each username from the prompt.
3. The exposed values are salted SHA-512-crypt hashes, identifiable by the `$6$` prefix. They are not raw SHA-512 digests. With no explicit rounds parameter, this format defaults to 5,000 rounds.
4. Save either one hash per line or `username:hash` records in a private file. Use a cracking tool's username option when supplying the latter format. Do not publish this file or include it in command output shared with the repository.

There were no password-bearing login submissions in this capture. Decryption reveals the stored hashes, so offline candidate testing is still required.

## Build and test candidates

Use the constraints to filter candidates, while treating birdwatching as a vocabulary hypothesis rather than a guaranteed password construction.

1. Start with dictionary entries and contextual vocabulary: bird common names, compound names, scientific names, and username-related terms. Deduplicate before applying expensive hash checks.
2. Generate variants with one uppercase character at every plausible position and one inserted or substituted special character. Include separators and possible digit suffixes. Do not assume the uppercase character comes first or the special character comes last.
3. Enforce the minimum length and count conditions after mutation. For an ASCII-oriented candidate generator, a filter can look like this:

   ```python
   import string

   # A space is worth testing because the prompt does not define "special".
   special = set(string.punctuation + " ")

   def fits_hint(candidate):
       allowed = set(string.ascii_letters + string.digits) | special
       return (
           len(candidate) >= 10
           and all(character in allowed for character in candidate)
           and sum(character in string.ascii_uppercase for character in candidate) == 1
           and sum(character in special for character in candidate) == 1
       )
   ```

   This is a search assumption, not proof that non-ASCII characters are impossible. Digits do not count as special characters under this filter. Apply capitalization and leetspeak transformations before validating the final candidate.
4. Test the private candidate file using the correct hash format. For a private `username:hash` file, either of these is a starting point; replace the local paths:

   ```bash
   hashcat -m 1800 --username /private/path/hashes.txt /private/path/candidates.txt
   john --format=sha512crypt --wordlist=/private/path/candidates.txt /private/path/hashes.txt
   ```

5. Preserve sessions and checkpoint files. Compare candidate count and measured throughput before launching larger searches. Five different salts require separate hashing work, and an unrestricted search of all strings of length ten or greater is impractical on the available CPU.
6. Verify any match by recomputing the complete salted hash with its original parameters. Record which username it belongs to. A plausible-looking word or an output file's existence is not a verified recovery.

## What was tried and what remains

Completed searches included a filtered public password list, common English words, bird-name vocabulary, username and context variants, capitalization at different positions, symbol insertion/replacement, selected number patterns, and selected leetspeak rules. Space characters and some relaxed interpretations of the hint were also tested. A focused pass applied capitalization and special-character mutations across common contextual words. None produced a verified match.

These searches do not exhaust the space allowed by the hint. Some larger candidate sets were interrupted, and the environmental limit was CPU throughput with no available GPU. Continue from saved checkpoints, refine candidate constructions using any additional challenge evidence, or move the same extracted hashes to suitable cracking hardware. Do not report guessed passwords or describe extraction as a completed password recovery.
