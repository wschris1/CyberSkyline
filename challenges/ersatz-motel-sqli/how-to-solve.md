# Ersatz Motel SQL Injection: how to solve

**Status:** Prompt recovered from a prior chat. No field, schema name, or password is verified in this guide.

1. Enumerate the reservation form's fields and normal request format on the authorized HTTPS instance. Save a baseline response privately.
2. Test one field at a time with small, reversible inputs that distinguish SQL interpretation from ordinary validation failures. Stay within the challenge's limits.
3. Identify the backend product using database-specific behavior supported by more than one observation. Avoid treating a generic server error as proof.
4. Use a narrow query plan to identify the target table and column, then extract only the requested admin credential. Keep all response-bearing payloads and values private.
5. Recheck each inferred name and the final credential against the original service or platform feedback. Document any uncertainty if the instance expires.

Do not reuse the challenge technique against unrelated motel or reservation systems.
