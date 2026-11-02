# Skill: encodings, cryptography, and password recovery

Begin with the original bytes, supplied source, and exact constraints. Keep outputs private. An alphabet or digest length suggests possibilities; it does not identify an algorithm conclusively.

## Decode without losing information

Distinguish representation from encryption. Base64, hex, URL encoding, Morse, and character-number mappings can wrap another layer. Preserve leading zeroes, padding, separators, capitalization, and whitespace until the format establishes their meaning. Store binary results as bytes rather than forcing UTF-8.

Keep a transformation ledger: input checksum/length, operation, parameters, output length, and validation. Where meaningful, reverse the transformation and compare to the original. If canonical encodings differ only in permitted whitespace or padding, compare decoded bytes and explain that difference.

For XOR and stream-cipher tasks, distinguish raw bytes from hex text, fixed versus repeating keys, feedback direction, register width, bit order, byte order, offsets, and initialization. Known plaintext recovers only the positions it covers. A reused script is not proof of reused key/nonce/keystream. Separate sessions may have different keys.

## Identify the actual password verifier

Read prefixes, file-format versions, application code, salts, iteration counts, challenge nonces, and MAC/tag structure. Match the full format to the installed tool's documented examples. Hashcat modes and John formats are not interchangeable labels. If the parser rejects an input, fix its format or mode before spending time on candidate generation.

For composed hashes, determine whether inner digests are raw binary or ASCII hex. For salted schemes, determine the exact ordering and encoding of every component. Use supplied tests or create a small known-input fixture to verify a custom checker before launching a large search. Python's `crypt` module is unavailable on some modern Python installations; do not assume it exists or silently replace its algorithm.

Prefer evidence-based dictionaries and transformations before a large offline search. Online guessing and fuzzing must follow the challenge's explicit limits. Keep an attempt budget, measured speed, and stopping condition; do not imply an unbounded keyspace will finish soon.

## Turn wording into exact constraints

“At least ten” gives a minimum, not a maximum. “Exactly one uppercase and exactly one special” is not the same as “contains uppercase and symbols.” Define whether digits are allowed, whether spaces count as special, and whether the domain is ASCII or Unicode from the prompt or code.

For a specifically established ASCII printable, no-space policy, this illustrative predicate implements those counts:

```python
import string

def fits_ascii_policy(candidate):
    allowed = string.ascii_letters + string.digits + string.punctuation
    return (
        len(candidate) >= 10
        and all(char in allowed for char in candidate)
        and sum(char in string.ascii_uppercase for char in candidate) == 1
        and sum(char in string.punctuation for char in candidate) == 1
    )
```

That alphabet is an explicit assumption, not a rule for every challenge. Ensure a selected mask or rule actually enforces the constraints at all positions. Track any imposed maximum as an incomplete search boundary.

## Verify fully

Compare the complete digest, protocol proof, or authenticated tag. A short archive password verifier can collide; verify the full authentication value and successfully inspect the decrypted container. Plausible plaintext and recognizable prefixes are candidate evidence, not sufficient proof.

Rehash/re-encrypt with the exact parameters or use an independent implementation. Check all recovered characters, not just the beginning. Preserve the requested complete message instead of extracting only a token. Never place passwords, answer hashes, recovered keystreams, or key-equivalent internal state in this public repository.

Related guides: [wordlists](../../challenges/wordlist-hashes/how-to-solve.md), [password constraints](../../challenges/password-hint-sheet/how-to-solve.md), [encrypted formats](../../challenges/encrypted-files/how-to-solve.md), [nested backups](../../challenges/encoded-backup/how-to-solve.md), [XOR feedback](../../challenges/cooking-with-this-xor-that/how-to-solve.md), [keystream reuse](../../challenges/archived-internal-memos/how-to-solve.md), and [time-seeded WPS](../../challenges/wps-time-seed/how-to-solve.md).

References: [Hashcat format guidance and examples](https://hashcat.net/wiki/doku.php?id=example_hashes) and [John documentation](https://www.openwall.com/john/doc/). Check examples for the installed release rather than copying a mode from an unrelated write-up.

## Repository helpers

The [encoding and key tools](../../tools/README.md#encoding-and-key-checks) support explicit decoding, known-key XOR, final-candidate filtering, and public-key structure checks. They do not establish a recovered password or cryptographic solution by themselves.
