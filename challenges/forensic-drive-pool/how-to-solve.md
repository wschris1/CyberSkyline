# Forensic Drive Pool: how to solve

**Status:** Prompt recovered from a prior chat. The drive image is unavailable here, so none of the eight values is verified by this guide.

1. Record the compressed image's checksum, inspect its signature, and decompress a working copy outside the checkout. Do not mount or modify the only copy.
2. Identify the partition table and filesystem from on-disk structures. Use the filesystem's native inspection tools to read pool name, identifier, size, scrub history, and snapshot metadata.
3. Convert the scrub timestamp from its recorded time zone and precision, then round to the nearest UTC minute. Distinguish a scrub's start time from its completion time.
4. List snapshots and protection properties before extracting files. Reconstruct the full snapshot name from the tool output, including pool and dataset components.
5. Extract each candidate flag from the appropriate live dataset or snapshot and verify the bytes against the original image. Keep extracted data and final flags private.

A screenshot or shortened command output may omit metadata needed for an exact answer.
