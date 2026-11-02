# Friendly Archive Upload: how to solve

**Status:** Prompt recovered from a prior chat. The two passwords and flag are omitted and have not been independently verified for this guide.

1. Preserve the encoded upload. Determine its representation, decode it once, and inspect the resulting file signature before assuming that it is a valid ZIP.
2. Inventory archive entries and encryption methods without extracting to the checkout. Use the policy and date hint to build a bounded candidate set; count candidates and record tested coverage.
3. Confirm any archive password by decrypting and verifying full entry integrity. Inspect the inner file's encryption format and repeat candidate testing for its separate password.
4. Decode the inner content and verify the final flag against the original bytes. Keep passwords, extracted content, and flag private.

The two layers may use different passwords. A successful ZIP listing does not prove the inner file was decrypted.
