# Nginx Basic Authentication: how to solve

## Steps

1. Read the matching `server` block. Combine its `root` directive with the protected `location` URI to determine the filesystem directory; the URI alone is not a filesystem path.
2. Follow `auth_basic_user_file` to the supplied `htpasswd` file. Identify the hash scheme from its prefix before selecting a cracking tool.
3. Apply the five-letter constraint to a dictionary first. Then use a mask attack for lowercase candidates and common capitalization patterns. John the Ripper's `md5crypt` format handles Apache MD5 hashes; forked workers reduce the time needed for exhaustive masks.
4. Verify a recovered candidate by hashing it again with the stored salt. Since only one account password is requested, stop after one full match.
5. Inspect more specific nested `location` blocks for `auth_basic off`, which marks a subdirectory excluded from the parent password requirement.
