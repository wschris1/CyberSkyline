# Encrypted Files: how to solve

## Steps

1. Identify each format from its header rather than its extension: `file` and a short hex or text preview are enough to choose the right verifier.
2. For an Ansible Vault payload, decode the outer hex, split the salt, authentication tag, and ciphertext, derive the keys with its PBKDF2 settings, and compare the authentication tag for each candidate.
3. For a PuTTY private key, parse the public and encrypted private blobs. Derive the encryption key from the passphrase, decrypt the private blob, and confirm the private-key MAC. The RSA key size determines plausible private-field lengths; do not assume every key is 2,048 bits.
4. For a 7z archive, inspect the AES coder properties and test the candidate by extracting or checking the contained file's CRC. The key derivation is deliberately expensive, so start with likely candidates and use a compiled checker for a large list.
5. Validate every result with a second implementation or a successful authenticated extraction.
