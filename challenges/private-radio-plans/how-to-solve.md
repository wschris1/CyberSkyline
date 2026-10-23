# Private Radio Plans: how to solve

## Approach

Read the channel details from the QR code, decode the MeshCore frame structure, verify the channel traffic cryptographically, then combine the node advertisement with the decrypted conversation.

## Steps

1. Decode the QR image in `IMAGES/`. Its URI identifies the MeshCore channel and carries a 16-byte channel secret. Keep the actual secret out of the write-up.
2. Convert each line in `IMAGES/raw_packets.txt` from hex to bytes. The first header byte contains the payload type and route type; the next path-length byte determines where the payload begins. Separate node advertisements from group-text frames.
3. For group text, the payload begins with a one-byte channel hash and two-byte cipher MAC, followed by ciphertext. Verify that the channel hash equals the first byte of SHA-256 of the QR secret. Verify the cipher MAC against the first two bytes of HMAC-SHA256 over the ciphertext with that secret.
4. Decrypt the ciphertext in 16-byte AES-128 ECB blocks using the channel secret. In the plaintext, skip the four-byte timestamp and one-byte flag field, then read the UTF-8 `sender: message` text and discard zero padding.
5. Parse Catherine's node advertisement. Its application-data flags mark the presence of a location and name. Read latitude and longitude as signed little-endian 32-bit integers and divide by one million. Locate those coordinates on a map to determine the requested major city and regional abbreviation.
6. Read the conversation for the item and the border agency mentioned. For the shop question, search specialty retailers near the advertised coordinates that sell the item, then compare locations rather than selecting a shop solely by name.

## Protocol references

- [MeshCore packet format](https://docs.meshcore.io/packet_format/)
- [MeshCore payload format](https://docs.meshcore.io/payloads/)

