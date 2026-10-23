# Encoded Code Words: how to solve

## Approach

Identify the encoding from its alphabet and delimiters, then preserve the exact character sequence when submitting. A decoding step can reveal another encoding rather than the final text.

## Steps

1. For the hyphen-separated integers, map 1 through 26 to A through Z. The hyphens separate letters; they do not imply spaces. Join the decoded letters directly.
2. For the dot-and-dash sequence, split on the existing spaces between Morse symbols and translate each symbol with an International Morse table. Do not add word spaces unless the source has a word separator.
3. For the lowercase string, rotate each alphabetic character by 13 positions. Preserve the original case and any nonletters.
4. For the longer dot-and-dash sequence, first decode Morse. Its repeated Morse hyphen character separates decimal integers. Convert those integers with the same 1-to-26 alphabet mapping used in step 1.
5. Check every output character against the original separators before entering it. In this challenge, extra spaces change the submitted string.

