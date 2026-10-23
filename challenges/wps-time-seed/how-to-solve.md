# Time-Seeded WPS Handshake: how to solve

## Approach

Parse WPS M1 through M3, validate the supplied registrar private key against M2, derive the WPS authentication key, reconstruct the time-seeded nonce stream, and test each PIN half against the M3 hashes. Keep every recovered identifier and PIN out of the public guide.

## Steps

1. Open the PCAP and isolate the EAPOL WPS exchange. WPS attributes are type-length-value records. In M1, read the enrollee MAC, manufacturer, model, enrollee nonce, and enrollee DH public key. The public key's 192-byte length identifies the 1536-bit MODP group.
2. Read the registrar nonce and public key from M2, and the two enrollee hashes from M3. Parse the supplied private key as a big-endian integer. Verify that raising generator 2 to that exponent modulo the 1536-bit group prime reproduces the M2 public key.
3. Compute the shared secret from the M1 public key and registrar private exponent. Hash its 192-byte big-endian representation with SHA-256 to obtain `DHKey`. Derive `KDK = HMAC-SHA256(DHKey, enrollee_nonce || enrollee_MAC || registrar_nonce)`. Run the WPS key-derivation function with label `Wi-Fi Easy and Secure Key Derivation`; its first 32 output bytes are `AuthKey`.
4. Validate `AuthKey` by recalculating the truncated authenticators at the ends of M2 and M3. Each authenticates the preceding message's WPS attributes concatenated with the current message's attributes before its authenticator TLV. This check catches errors in byte order, key derivation, or frame boundaries.
5. Search Unix-second seeds near the packet timestamps. For each seed, advance the 32-bit recurrence `state = (1103515245 * state + 12345) mod 2^32`, taking `(state >> 16) & 0xff` for each output byte. Match the resulting stream against the public nonces and UUIDs to establish the seed and byte offsets.
6. Take the next two 16-byte secret nonces from the matched stream. For this capture, test each four-character ASCII PIN half directly in `HMAC-SHA256(AuthKey, secret_nonce || PIN_half || PKE || PKR)` against its corresponding M3 hash. This is the hash construction observed in this exercise; verify it against both hashes rather than assuming another implementation's PIN preprocessing.
7. Combine the matching halves without a separator. Independently check the standard WPS check digit of the resulting eight-digit PIN before submitting it to the challenge platform.

