# Archived Internal Memos: how to solve

## Test for reused keystream bytes

A stream encryption operation combines plaintext with a keystream:

```text
ciphertext = plaintext XOR keystream
```

If two messages reuse the same keystream at the same positions, XORing their ciphertexts cancels it. A known plaintext can then recover the corresponding part of the other message:

```text
other_plaintext = other_ciphertext XOR known_ciphertext XOR known_plaintext
```

The prompt does not identify which ciphertext matches the recovered memo. Test each possible assignment. Using the same script does not by itself prove that every ciphertext shares a keystream; assess each pair independently.

## Recover candidate messages

1. Base64-decode the three strings from `question.md` into bytes.
2. Encode the exact known plaintext as UTF-8, preserving spaces and punctuation.
3. XOR it with each possible known ciphertext to obtain candidate keystream prefixes.
4. Apply each candidate prefix to the remaining ciphertexts.
5. Inspect the candidates privately for coherent prose across the recovered span.

```python
import base64

def xor_bytes(a, b):
    return bytes(x ^ y for x, y in zip(a, b))

def recover_candidates(encoded_messages, known_text):
    messages = [base64.b64decode(s, validate=True) for s in encoded_messages]
    known = known_text.encode("utf-8")
    candidates = {}
    for known_index, known_ciphertext in enumerate(messages):
        stream_prefix = xor_bytes(known_ciphertext, known)
        for target_index, target_ciphertext in enumerate(messages):
            if target_index != known_index:
                candidates[known_index, target_index] = xor_bytes(
                    target_ciphertext, stream_prefix
                )
    return candidates
```

This recovers only positions covered by both the known plaintext and the target ciphertext. It does not establish the remaining plaintext or the original secret key. Do not invent an ending or assume a particular padding scheme to extend it.

## Check your work

The useful candidate should contain readable language throughout its recovered portion. XORing that candidate with its ciphertext should reproduce the same keystream prefix obtained from the known memo. The ordered pair can appear in either direction because the XOR expression is symmetric; readable output alone need not identify which member was the backed-up memo.

The supplied inputs were checked for a readable reused-keystream candidate. Recovered prose, keystream bytes, and the submission value are excluded from this guide.
