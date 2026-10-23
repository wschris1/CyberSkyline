# Water-Damaged Barcode: how to solve

## Approach

Use the original image, not a resized preview. The bars have two widths and match Codabar. Each character has seven alternating bar and space runs, separated from the next character by a narrow space. Codabar does not require a check digit, so a checksum must be verified against the issuing institution's rules before relying on it.

## Steps

1. Read the visible printed characters and inspect a horizontal scanline through the bars. Measure the narrow and wide runs, then compare the opening and closing characters with a Codabar character table.
2. Count the data characters between the start and stop symbols. Map each complete set of seven runs to a character. This exposes more of the number than the printed text alone.
3. For the fully covered character, record the visible run fragments and use them to rule out incompatible digits. In a common 14-digit library format, the first digit denotes an item or patron, the next four identify the institution, the next eight are a sequence, and the last is a Mod 10 check digit. Confirm that this format fits the observed code before using it.
4. A documented library Mod 10 method doubles digits in odd positions, counted from the left, and leaves even positions unchanged. Add the digits of any two-digit products, sum the results, and find the digit needed to reach the next multiple of ten. Render that candidate as Codabar and check it against the surviving bar fragments.
5. Search for the institution prefix in regional library registries and catalogs. Library prefixes are not nationally unique, so compare independent examples from the same institution before deciding which one likely issued the code, then confirm its U.S. state.
6. Submit the digit and institution to the CTF platform. Keep those final responses out of this repository.

## References

- [American Library Association: Bar Codes in Libraries](https://www.ala.org/tools/bar-codes-libraries) explains the item/patron digit, four-digit library identifier, and why an identifier alone may not be unique.
- [Maine InfoNet: Maine Barcode Symbol Registry](https://www.maineinfonet.org/mainecat/maine-barcode-symbol-registry/) documents one regional 14-digit Codabar convention. Its registry is an example of the format, not evidence that this sticker came from Maine.
- [ResourceMate: How is the Mod10 check digit calculated?](https://www.resourcemate.com/support/help/help/HowIsTheMod10CheckDigitCalculated.html) gives the calculation and a 14-digit example.
