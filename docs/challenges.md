# wschris CyberSecurity challenge library

[Home](../README.md) · [Investigation playbook](ctf-playbook.md) · [Tools](../tools/README.md) · [Skill playbooks](README.md)

Explore 38 challenge prompts with paired method guides. Guides describe methods and verification steps; read each one for its limits and any unresolved work. Final answers and raw evidence stay private.

| Category | Guides | Focus |
| --- | ---: | --- |
| [Network, services, and logs](#network-services-and-logs) | 7 | Traffic, services, and event records |
| [Encoding, cryptography, and passwords](#encoding-cryptography-and-passwords) | 13 | Encodings, keys, and candidate verification |
| [Web and browser evidence](#web-and-browser-evidence) | 6 | Browser records and authorized web labs |
| [Files, images, and reverse engineering](#files-images-and-reverse-engineering) | 6 | Binary artifacts and reconstruction |
| [OSINT and research](#osint-and-research) | 6 | Public and historical sources |

## Network, services, and logs

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Service Enumeration](../challenges/service-enumeration/question.md) | [Service Enumeration method](../challenges/service-enumeration/how-to-solve.md) | Ports, protocol greetings, exact banners, and HTTP headers |
| [Hercules Compliance Audit](../challenges/hercules-compliance-audit/question.md) | [Hercules Compliance Audit method](../challenges/hercules-compliance-audit/how-to-solve.md) | SMB, scanner profiles, SSH identity, and permissions; incomplete |
| [Unauthorized Network Services](../challenges/unauthorized-network-services/question.md) | [Unauthorized Network Services method](../challenges/unauthorized-network-services/how-to-solve.md) | Zeek correlation and service policy |
| [Conference Network Capture](../challenges/conference-network-capture/question.md) | [Conference Network Capture method](../challenges/conference-network-capture/how-to-solve.md) | Network capture and device investigation |
| [Private Radio Plans](../challenges/private-radio-plans/question.md) | [Private Radio Plans method](../challenges/private-radio-plans/how-to-solve.md) | Packet inspection and recovered communications |
| [Public WordPress Access Log](../challenges/public-wordpress-log/question.md) | [Public WordPress Access Log method](../challenges/public-wordpress-log/how-to-solve.md) | Web access logs and request reconstruction |
| [Choclympic Peaks Product Leak](../challenges/choclympic-leak/question.md) | [Choclympic Peaks Product Leak method](../challenges/choclympic-leak/how-to-solve.md) | Correlating evidence of a product-data leak |

## Encoding, cryptography, and passwords

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Archived Internal Memos](../challenges/archived-internal-memos/question.md) | [Archived Internal Memos method](../challenges/archived-internal-memos/how-to-solve.md) | Known plaintext and keystream reuse |
| [Cooking With This XOR That (Medium)](../challenges/cooking-with-this-xor-that/question.md) | [Cooking With This XOR That (Medium) method](../challenges/cooking-with-this-xor-that/how-to-solve.md) | XOR feedback schemes |
| [Live Relay Cipher](../challenges/live-relay-cipher/question.md) | [Live Relay Cipher method](../challenges/live-relay-cipher/how-to-solve.md) | Generator state and framed binary traffic |
| [Encoded Backup](../challenges/encoded-backup/question.md) | [Encoded Backup method](../challenges/encoded-backup/how-to-solve.md) | Layered representation and backup analysis |
| [Encoded Code Words](../challenges/encoded-code-words/question.md) | [Encoded Code Words method](../challenges/encoded-code-words/how-to-solve.md) | Identifying and reversing encodings |
| [Encrypted Files](../challenges/encrypted-files/question.md) | [Encrypted Files method](../challenges/encrypted-files/how-to-solve.md) | Format identification and verified decryption |
| [Intercepted Secure Message](../challenges/intercepted-secure-message/question.md) | [Intercepted Secure Message method](../challenges/intercepted-secure-message/how-to-solve.md) | Phonetic words and grouped symbols |
| [Wordlist Hashes](../challenges/wordlist-hashes/question.md) | [Wordlist Hashes method](../challenges/wordlist-hashes/how-to-solve.md) | Candidate construction and full-hash checks |
| [Password Hint Sheet](../challenges/password-hint-sheet/question.md) | [Password Hint Sheet method](../challenges/password-hint-sheet/how-to-solve.md) | Constraints, candidate coverage, and validation |
| [Time-Seeded WPS Handshake](../challenges/wps-time-seed/question.md) | [Time-Seeded WPS Handshake method](../challenges/wps-time-seed/how-to-solve.md) | Time-derived seeds and protocol verification |
| [Encrypted SQLite Backup](../challenges/encrypted-sqlite-backup/question.md) | [Encrypted SQLite Backup method](../challenges/encrypted-sqlite-backup/how-to-solve.md) | Identify an encrypted database, test password candidates, and inspect its records |
| [Encryption Validation Service](../challenges/encryption-validation-service/question.md) | [Encryption Validation Service method](../challenges/encryption-validation-service/how-to-solve.md) | Read supplied crypto code and test a validation weakness in an authorized service |
| [Friendly Archive Upload](../challenges/friendly-archive-upload/question.md) | [Friendly Archive Upload method](../challenges/friendly-archive-upload/how-to-solve.md) | Recover layered archive credentials from a failed encoded upload |

## Web and browser evidence

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Browser History Investigation](../challenges/browser-history-investigation/question.md) | [Browser History Investigation method](../challenges/browser-history-investigation/how-to-solve.md) | Database schemas, visits, and timestamps |
| [Nginx Basic Authentication](../challenges/nginx-basic-auth/question.md) | [Nginx Basic Authentication method](../challenges/nginx-basic-auth/how-to-solve.md) | Authentication format and candidate verification |
| [Cyber Command](../challenges/cyber-command/question.md) | [Cyber Command method](../challenges/cyber-command/how-to-solve.md) | TLS decryption and authentication evidence; password recovery incomplete |
| [Cyber Command: admin flag](../challenges/cyber-command-admin-flag/question.md) | [Cyber Command: admin flag method](../challenges/cyber-command-admin-flag/how-to-solve.md) | Redirects, framing, and CSRF in the supplied lab |
| [Shipping Order Web App](../challenges/shipping-order-web-app/question.md) | [Shipping Order Web App method](../challenges/shipping-order-web-app/how-to-solve.md) | Inspect a shipping web app and recover a restricted order's arrival information |
| [Ersatz Motel SQL Injection](../challenges/ersatz-motel-sqli/question.md) | [Ersatz Motel SQL Injection method](../challenges/ersatz-motel-sqli/how-to-solve.md) | Trace a reservation form's SQL injection to a targeted credential |

## Files, images, and reverse engineering

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Blurred Messages](../challenges/blurred-messages/question.md) | [Blurred Messages method](../challenges/blurred-messages/how-to-solve.md) | Font matching and full-image reconstruction |
| [Scrambled Python Code](../challenges/scrambled-python-code/question.md) | [Scrambled Python Code method](../challenges/scrambled-python-code/how-to-solve.md) | Bytecode inspection and input-check inversion |
| [Water-Damaged Barcode](../challenges/water-damaged-barcode/question.md) | [Water-Damaged Barcode method](../challenges/water-damaged-barcode/how-to-solve.md) | Barcode structure and independent identification |
| [YARA Secret Hunt](../challenges/yara-secret-hunt/question.md) | [YARA Secret Hunt method](../challenges/yara-secret-hunt/how-to-solve.md) | Rules, file triage, and matching evidence |
| [Forensic Drive Pool](../challenges/forensic-drive-pool/question.md) | [Forensic Drive Pool method](../challenges/forensic-drive-pool/how-to-solve.md) | Inspect a storage pool, snapshots, scrub time, and recovered files |
| [Remote Desktop Bitmap Cache](../challenges/remote-desktop-bitmap-cache/question.md) | [Remote Desktop Bitmap Cache method](../challenges/remote-desktop-bitmap-cache/how-to-solve.md) | Parse cached bitmaps and correlate session metadata |

## OSINT and research

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Cybersecurity Community](../challenges/cybersecurity-community/question.md) | [Cybersecurity Community method](../challenges/cybersecurity-community/how-to-solve.md) | Primary-source research and terminology |
| [Device Default Passwords](../challenges/device-default-passwords/question.md) | [Device Default Passwords method](../challenges/device-default-passwords/how-to-solve.md) | Device identification and vendor documentation |
| [Map Itinerary](../challenges/map-itinerary/question.md) | [Map Itinerary method](../challenges/map-itinerary/how-to-solve.md) | Geographic clues and route reconstruction |
| [Vessel Tracking](../challenges/vessel-tracking/question.md) | [Vessel Tracking method](../challenges/vessel-tracking/how-to-solve.md) | Historical location and vessel records |
| [This Way Pleaae!](../challenges/this-way-pleaae/question.md) | [This Way Pleaae! method](../challenges/this-way-pleaae/how-to-solve.md) | Map courier location clues to a program, office history, and a coded meeting point |
| [Censored Social Post Flag](../challenges/censored-social-flag/question.md) | [Censored Social Post Flag method](../challenges/censored-social-flag/how-to-solve.md) | Trace an old censored social post to an uncensored source |

