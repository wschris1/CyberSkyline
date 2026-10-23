# Encoded Backup: how to solve

## Steps

1. Check the text for base64 syntax, decode it, and inspect the result with `file` and `zipfile`. List entries without extracting them first.
2. The archive's AES entry supplies a salt, a two-byte password verifier, ciphertext, and an authentication tag. Use the stated password rules to filter a wordlist, derive the key for each candidate, and validate the full tag after a verifier match. The two-byte verifier alone can produce false positives.
3. Decrypt the archive only after authentication succeeds. Inspect the inner file's *magic bytes*: an Office document can be an encrypted OLE container even when its filename ends in `.docx`.
4. Use `msoffcrypto-tool` to verify the Office password and decrypt the document. For a compiled password checker, compare its output against a published test vector and copy the file's salt and verifier bytes programmatically; one mistyped byte makes every candidate fail.
5. Confirm the resulting file opens as an OOXML ZIP. Read `word/document.xml`, combine text runs in paragraph order, and search for the flag format specified by the challenge.
