# Encrypted SQLite Backup: how to solve

**Status:** Prompt recovered from a prior chat. The password and database contents have not been verified for this guide.

1. Preserve the database and password-list originals. Inspect the file header, page size, reserved bytes, and any metadata before selecting an encryption format. An unreadable SQLite header alone does not identify a specific fork.
2. Identify candidate format versions and key-derivation settings from the supplied evidence. Use the older password list as a bounded candidate set; record any mutations and the tested coverage.
3. For each candidate, derive the key using the format's documented parameters and validate a complete page, including its authentication value where available. A plausible decrypted prefix is insufficient.
4. Open a verified copy with a compatible library, inspect the schema, and locate the flag record. Keep the password, decrypted pages, and flag private.

A confirmed format name from platform feedback does not prove that a candidate password or flag is correct.
