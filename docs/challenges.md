# wschris CyberSecurity challenge library

[Home](../README.md) · [Investigation playbook](ctf-playbook.md) · [Tools](../tools/README.md) · [Skill playbooks](README.md)

Explore 38 challenge prompts with paired method guides. Each guide records its own status, verification steps, and limits. Final answers and raw evidence stay private.

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
| [Service Enumeration](../challenges/service-enumeration/question.md) | [Read guide](../challenges/service-enumeration/how-to-solve.md) | Ports, protocol greetings, exact banners, and HTTP headers |
| [Hercules Compliance Audit](../challenges/hercules-compliance-audit/question.md) | [Read guide](../challenges/hercules-compliance-audit/how-to-solve.md) | SMB, scanner profiles, SSH identity, and permissions; incomplete |
| [Unauthorized Network Services](../challenges/unauthorized-network-services/question.md) | [Read guide](../challenges/unauthorized-network-services/how-to-solve.md) | Zeek correlation and service policy |
| [Conference Network Capture](../challenges/conference-network-capture/question.md) | [Read guide](../challenges/conference-network-capture/how-to-solve.md) | Network capture and device investigation |
| [Private Radio Plans](../challenges/private-radio-plans/question.md) | [Read guide](../challenges/private-radio-plans/how-to-solve.md) | Packet inspection and recovered communications |
| [Public WordPress Access Log](../challenges/public-wordpress-log/question.md) | [Read guide](../challenges/public-wordpress-log/how-to-solve.md) | Web access logs and request reconstruction |
| [Choclympic Peaks Product Leak](../challenges/choclympic-leak/question.md) | [Read guide](../challenges/choclympic-leak/how-to-solve.md) | Correlating evidence of a product-data leak |

## Encoding, cryptography, and passwords

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Archived Internal Memos](../challenges/archived-internal-memos/question.md) | [Read guide](../challenges/archived-internal-memos/how-to-solve.md) | Known plaintext and keystream reuse |
| [Cooking With This XOR That (Medium)](../challenges/cooking-with-this-xor-that/question.md) | [Read guide](../challenges/cooking-with-this-xor-that/how-to-solve.md) | XOR feedback schemes |
| [Live Relay Cipher](../challenges/live-relay-cipher/question.md) | [Read guide](../challenges/live-relay-cipher/how-to-solve.md) | Generator state and framed binary traffic |
| [Encoded Backup](../challenges/encoded-backup/question.md) | [Read guide](../challenges/encoded-backup/how-to-solve.md) | Layered representation and backup analysis |
| [Encoded Code Words](../challenges/encoded-code-words/question.md) | [Read guide](../challenges/encoded-code-words/how-to-solve.md) | Identifying and reversing encodings |
| [Encrypted Files](../challenges/encrypted-files/question.md) | [Read guide](../challenges/encrypted-files/how-to-solve.md) | Format identification and verified decryption |
| [Intercepted Secure Message](../challenges/intercepted-secure-message/question.md) | [Read guide](../challenges/intercepted-secure-message/how-to-solve.md) | Phonetic words and grouped symbols |
| [Wordlist Hashes](../challenges/wordlist-hashes/question.md) | [Read guide](../challenges/wordlist-hashes/how-to-solve.md) | Candidate construction and full-hash checks |
| [Password Hint Sheet](../challenges/password-hint-sheet/question.md) | [Read guide](../challenges/password-hint-sheet/how-to-solve.md) | Constraints, candidate coverage, and validation |
| [Time-Seeded WPS Handshake](../challenges/wps-time-seed/question.md) | [Read guide](../challenges/wps-time-seed/how-to-solve.md) | Time-derived seeds and protocol verification |
| [Encrypted SQLite Backup](../challenges/encrypted-sqlite-backup/question.md) | [Read guide](../challenges/encrypted-sqlite-backup/how-to-solve.md) | Identify an encrypted database, test password candidates, and inspect its records |
| [Encryption Validation Service](../challenges/encryption-validation-service/question.md) | [Read guide](../challenges/encryption-validation-service/how-to-solve.md) | Read supplied crypto code and test a validation weakness in an authorized service |
| [Friendly Archive Upload](../challenges/friendly-archive-upload/question.md) | [Read guide](../challenges/friendly-archive-upload/how-to-solve.md) | Recover layered archive credentials from a failed encoded upload |

## Web and browser evidence

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Browser History Investigation](../challenges/browser-history-investigation/question.md) | [Read guide](../challenges/browser-history-investigation/how-to-solve.md) | Database schemas, visits, and timestamps |
| [Nginx Basic Authentication](../challenges/nginx-basic-auth/question.md) | [Read guide](../challenges/nginx-basic-auth/how-to-solve.md) | Authentication format and candidate verification |
| [Cyber Command](../challenges/cyber-command/question.md) | [Read guide](../challenges/cyber-command/how-to-solve.md) | TLS decryption and authentication evidence; password recovery incomplete |
| [Cyber Command: admin flag](../challenges/cyber-command-admin-flag/question.md) | [Read guide](../challenges/cyber-command-admin-flag/how-to-solve.md) | Redirects, framing, and CSRF in the supplied lab |
| [Shipping Order Web App](../challenges/shipping-order-web-app/question.md) | [Read guide](../challenges/shipping-order-web-app/how-to-solve.md) | Inspect a shipping web app and recover a restricted order's arrival information |
| [Ersatz Motel SQL Injection](../challenges/ersatz-motel-sqli/question.md) | [Read guide](../challenges/ersatz-motel-sqli/how-to-solve.md) | Trace a reservation form's SQL injection to a targeted credential |

## Files, images, and reverse engineering

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Blurred Messages](../challenges/blurred-messages/question.md) | [Read guide](../challenges/blurred-messages/how-to-solve.md) | Font matching and full-image reconstruction |
| [Scrambled Python Code](../challenges/scrambled-python-code/question.md) | [Read guide](../challenges/scrambled-python-code/how-to-solve.md) | Bytecode inspection and input-check inversion |
| [Water-Damaged Barcode](../challenges/water-damaged-barcode/question.md) | [Read guide](../challenges/water-damaged-barcode/how-to-solve.md) | Barcode structure and independent identification |
| [YARA Secret Hunt](../challenges/yara-secret-hunt/question.md) | [Read guide](../challenges/yara-secret-hunt/how-to-solve.md) | Rules, file triage, and matching evidence |
| [Forensic Drive Pool](../challenges/forensic-drive-pool/question.md) | [Read guide](../challenges/forensic-drive-pool/how-to-solve.md) | Inspect a storage pool, snapshots, scrub time, and recovered files |
| [Remote Desktop Bitmap Cache](../challenges/remote-desktop-bitmap-cache/question.md) | [Read guide](../challenges/remote-desktop-bitmap-cache/how-to-solve.md) | Parse cached bitmaps and correlate session metadata |

## OSINT and research

| Challenge | Method guide | Focus |
| --- | --- | --- |
| [Cybersecurity Community](../challenges/cybersecurity-community/question.md) | [Read guide](../challenges/cybersecurity-community/how-to-solve.md) | Primary-source research and terminology |
| [Device Default Passwords](../challenges/device-default-passwords/question.md) | [Read guide](../challenges/device-default-passwords/how-to-solve.md) | Device identification and vendor documentation |
| [Map Itinerary](../challenges/map-itinerary/question.md) | [Read guide](../challenges/map-itinerary/how-to-solve.md) | Geographic clues and route reconstruction |
| [Vessel Tracking](../challenges/vessel-tracking/question.md) | [Read guide](../challenges/vessel-tracking/how-to-solve.md) | Historical location and vessel records |
| [This Way Pleaae!](../challenges/this-way-pleaae/question.md) | [Read guide](../challenges/this-way-pleaae/how-to-solve.md) | Map courier location clues to a program, office history, and a coded meeting point |
| [Censored Social Post Flag](../challenges/censored-social-flag/question.md) | [Read guide](../challenges/censored-social-flag/how-to-solve.md) | Trace an old censored social post to an uncensored source |

