# Merkle Tree \(Medium\) — Question 4

**Event:** NCL Fall 2026 Team Game

**Category:** Cryptography

**Level:** medium

**Source:** https://cyberskyline.com/module/6a1729e7d4551af5a8772a55/6a5fb318174f36bdf883acd5/6a39a6b7e1aa579fc845757c

## Prompt

A ledger of 8 transactions is protected by a Merkle tree - a cryptographic structure where any change to a record cascades upward, corrupting every hash on the path to the root \(which is right at the top\!\). Someone has tampered with one of the entries. The root hash no longer matches the trusted value on file. Examine the tree, find the bad record, and reconstruct what it should look like.




Use ` verify.py ` to check whether a proposed hash for a given leaf produces the ` expected_root. `

## Question 4

Q4 - 10 points



Each transaction has the format ` tx:SENDER->RECEIVER:AMOUNT `. Which field was tampered with?

## Referenced files

- corrupted-tree.json
- audit\_paths.json

Open the source challenge to download its original files.

---

Imported question text. Response fields, submission history, and solution guides are excluded.
