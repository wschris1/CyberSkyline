# Wordlist Hashes: how to solve

## Steps

1. Count hex characters to determine likely digest families: 40 suggests SHA-1, 64 suggests SHA-256, and 128 suggests SHA-512.
2. Read the named candidate lists as bytes, trim only line endings, and hash each candidate with the matching algorithm. Compare the complete digest, not a prefix.
3. Hash each recovered candidate once more independently before reporting it. Preserve capitalization, digits, and punctuation exactly.

   ```python
   import hashlib

   digest = hashlib.sha256(candidate_bytes).hexdigest()
   assert digest == target_hex
   ```
