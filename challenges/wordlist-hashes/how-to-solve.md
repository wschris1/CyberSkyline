# Wordlist Hashes: how to solve

## Steps

1. Count hex characters to determine likely digest families: 40 suggests SHA-1, 64 suggests SHA-256, and 128 suggests SHA-512.
2. Read the named candidate lists as bytes, trim only line endings, and hash each candidate with the matching algorithm. Compare the complete digest, not a prefix.
3. Verify each candidate match against the full stored digest using a second implementation or the original challenge program, distinct from the candidate search. Compare the exact input bytes, including line-ending handling. Preserve capitalization, digits, and punctuation. If an independent check is unavailable, state that limit instead of calling a repeated run independent.

   The following is one implementation for a SHA-256 full-digest check; it counts as independent only if the candidate search used a different implementation.

   ```python
   import hashlib

   digest = hashlib.sha256(candidate_bytes).hexdigest()
   assert digest == target_hex
   ```
