# Blurred Messages: how to solve

## Approach

The clear example provides a font and layout reference. The blurred line retains measurable differences between rendered characters. Recover the text by finding a rendering model that reproduces those pixels, using the SSH key format to constrain the search.

Work from the original PNGs, preserving their dimensions. Screenshots, resizing, and recompression introduce changes that make comparisons less reliable. Keep recovered text and comparison images outside this repository.

## Identify the font

1. Inspect the clear image at its original size. The regular character spacing suggests a monospaced font. Use visible letters and the known SSH algorithm prefix as reference text.
2. Obtain candidate monospaced families from Google Fonts and render the reference text with Pillow/FreeType. Vary font size, available width/weight variants, and horizontal and vertical offsets.
3. Compare each rendered crop to the clear reference using pixel error or normalized correlation. Use several distinctive glyphs and the full known prefix: a short word or one similar-looking letter is not sufficient.
4. Refine the best candidates at their native spacing. Record the winning family privately for Q1. Do not assume a website's display name and a font file's internal style name are identical.

## Calibrate the blur and layout

1. Render the known prefix with the selected font. Measure character advance and baseline rather than rounding every character to an integer cell.
2. Search crop offsets, font size, and Gaussian blur strength to reproduce the corresponding part of the blurred image. Use floating-point grayscale arrays for scoring.
3. Minimize mean squared error between the observed and simulated pixels. Inspect residuals for shifted edges or incorrect spacing before attempting unknown characters.
4. In this analysis, the flag was supplied and confirmed separately by the participant. That confirmed substring provided another alignment anchor. Do not describe it as an independently recovered result of the key search. Without such an anchor, the comment needs its own search and validation.

## Recover the Base64 portion

An OpenSSH public key line contains an algorithm label, a Base64-encoded binary blob, and an optional comment. The algorithm label and serialized type/length fields constrain the beginning of the blob. The unknown public-key bytes must be recovered from the pixels; generating a different valid key would not solve the problem.

1. Locate the key and comment boundaries using the fitted character advance. Restrict unknown encoded characters to the Base64 alphabet.
2. Render a template for every candidate character at each position, using the measured subpixel placement. Apply the calibrated blur and compare local windows with the observed line.
3. Account for neighboring characters. Blur spreads each glyph into adjacent cells, so choosing the best character independently at each position can give the wrong string.
4. Express squared pixel error as a sum of single-character costs and pairwise overlap costs. Determine how many neighboring positions overlap under the chosen finite blur support.
5. For the fitted model here, adjacent and next-adjacent positions mattered. A Viterbi-style dynamic program retained the previous two characters as its state. Each transition added a candidate character and the newly determined overlap costs; backtracking produced the lowest-error complete sequence.

Conceptually, for observed pixels `Y`, fixed rendered content `F`, and candidate glyph contributions `G`, minimize:

```text
||Y - F - sum(G[position, character])||²
```

Expanding the square gives the local and overlap costs used by the search. This reduces the search substantially compared with enumerating every possible complete key.

## Validate the complete reconstruction

1. Render the recovered line as a whole with the actual font layout engine. Apply the same crop and blur, then compare it with the original blurred image.
2. Check alternative spacing hypotheses against this full-line rendering. Small advance differences accumulate across a long line and can change the preferred characters. A low local template score alone is not enough.
3. Strictly Base64-decode the recovered blob. Parse its big-endian length-prefixed fields: the algorithm name and the public-key bytes. For this algorithm, verify the expected algorithm-name length, a 32-byte public-key field, and no unexplained trailing bytes.
4. Save only the algorithm label and encoded blob to a private `.pub` file and check that OpenSSH accepts it:

   ```bash
   ssh-keygen -lf /path/to/private-working-directory/recovered.pub
   ```

5. Require agreement between the format checks and the image comparison. A syntactically valid public key does not prove that it matches the image. Here, whole-line re-rendering resolved ambiguous character choices and reproduced the observed blurred pixels with very small residual error.

Submit the font family, confirmed flag, and public key in their respective fields. Omit the trailing comment from the public-key submission. Blurring is not reliable redaction: an opaque replacement that removes the underlying pixels is needed when publishing sensitive text.
