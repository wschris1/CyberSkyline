# Remote Desktop Bitmap Cache: how to solve

**Status:** Prompt recovered from a prior chat. The cache file is unavailable here; the counts and hidden flag are unverified.

1. Preserve the binary and identify its actual format by signature and structure. Parse cache records with a tool that reports malformed or truncated records.
2. Count complete bitmap records, then reconstruct images using the format's dimensions, pixel order, and compression rules. Validate the count with an independent parser or manual record walk.
3. Correlate session metadata with the bitmap timeline for the connection time and remote IPv4 address. Establish the timestamp's zone and format before converting it.
4. Define “uploaded to the remote client” from direction evidence, not image appearance. Because the question allows one attempt, verify the direction and count before submission.
5. Review reconstructed images at native resolution and confirm any proposed flag against original pixels. Keep the images and response private.

Bitmap cache contents alone may be insufficient to establish transfer direction or session metadata.
