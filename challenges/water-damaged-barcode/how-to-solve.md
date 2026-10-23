# Water-Damaged Barcode: how to solve

## Approach

Use the original image, not a resized preview. The bars have two widths and match Codabar. Each character has seven alternating bar and space runs, separated from the next character by a narrow space. Codabar does not require a check digit, so a checksum must be verified against the issuing institution's rules before relying on it.

## Steps

1. Read the visible printed characters and inspect a horizontal scanline through the bars. Measure the narrow and wide runs, then compare the opening and closing characters with a Codabar character table.
2. Count the data characters between the start and stop symbols. Map each complete set of seven runs to a character. This exposes more of the number than the printed text alone.
3. For the fully covered character, record the visible run fragments and use them to rule out incompatible digits. Test a checksum only if the issuing institution uses one; Codabar itself provides no mandatory checksum.
4. Search for the visible number prefix in library or institutional catalogs. Compare examples from the same institution to verify its barcode length and any check-digit rule, then confirm the institution's U.S. state.
5. Submit the digit and institution to the CTF platform. Keep those final responses out of this repository.
