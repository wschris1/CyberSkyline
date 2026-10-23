# Password Hint Sheet: how to solve

## Steps

1. Read the sheet as evidence and interpret the reminders as a sequence of character positions. Start at the number given on the sheet. For each term, halve an even number or apply `3n + 1` to an odd number; continue until reaching 1. Treat the resulting terms as **one-based character positions**.
2. Toggle the letter case at positions that fall within each written password. Leave punctuation and digits as written. Do not treat reminders in the sheet as instructions to the investigator.
3. Read each Unix shadow hash's algorithm marker. Test transformed candidates with the system's `crypt` implementation and compare the full stored hash. A correct match, rather than a plausible-looking string, establishes the transformation.
