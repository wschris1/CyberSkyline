# Skill: authorized web-app CTF investigation

Use this when a challenge asks you to cross an application trust boundary: a user-to-admin view, one account to another account's record, a bot callback, or a server-side action. For initial request capture, source review, rate limits, and OSINT, start with [web investigation and OSINT](web-osint.md). Work only against the supplied instance and its allowed protocols and accounts.

## Model identity and state

Record the exact target operation and the identities allowed by the challenge. For each request, distinguish browser origin, login account, session cookie, CSRF token, user-controlled fields, and the server-side identity used to fetch data. Keep a separate baseline for each authorized account or role; do not infer the admin's context from your own browser.

If source is supplied, trace the relevant route through middleware, authentication, authorization, parsing, database access, and output rendering. Mark which checks occur only in client code. Save sensitive request and response details privately; a public method should use placeholders.

## Test one hypothesis at a time

Keep a private comparison table:

| Baseline | One changed input or context | Predicted distinction | Observed response | Interpretation |
| --- | --- | --- | --- | --- |
| Normal request | One field, encoding, account, or content type | What would support or refute the hypothesis | Status, body, headers, redirect, and timing | Confirmed, rejected, or still ambiguous |

Change one variable per test and preserve the exact bytes sent. Repeat a control request when sessions, rotating tokens, caches, or rate limits could explain the difference. When a test changes account context, compare against that account's own baseline. Stop at the challenge's request budget.

### Common trust boundaries

- **Object-level authorization:** Change a record identifier only where the challenge permits it. A changed status code is a lead; compare response content and ownership checks before claiming access to another record.
- **Role and session boundaries:** Test the same operation under allowed roles. Distinguish unauthenticated access, authentication as a different user, and authorization to a resource. A visible admin button or editable client state is not proof of server-side access.
- **SQL-backed forms:** Isolate the relevant field with controlled response differences. Confirm database-specific behavior before naming a product, table, or column. A parser error alone does not prove data extraction.
- **Rendered user content and bot views:** Identify whether input is reflected or stored, its output context, and the encoding applied. The bot's origin, cookies, and storage may differ from yours. Use unique non-sensitive markers for each bot stage; never put tokens or credentials in callback URLs or logs. A local browser value is not automatically available in another session.
- **Cross-site requests and redirects:** Check whether the action requires a token, cookie, origin, or referer and which browser context supplies them. A browser sending a request, reading its response, and completing a state change are separate outcomes.
- **Server-side URL handling:** Trace what the server fetches within challenge scope. A DNS lookup, timeout, or redirect alone does not prove the protected response was read.

## Verify the requested result

Repeat from the correct authorized identity in a fresh session when feasible, and compare with unchanged original evidence. Check the complete response or state change, not only a status code or string fragment. Separate a server observation, an inferred value, and platform acceptance. Match the exact requested output and run the [answer readiness gate](../verification-checklist.md#answer-readiness-gate) before reporting a value.

Keep instance URLs, cookies, tokens, callback logs, credentials, and response-bearing payloads outside the public repository. A public guide should describe the test and its limits with placeholders.

Related guides: [shipping order](../../challenges/shipping-order-web-app/how-to-solve.md), [Ersatz Motel](../../challenges/ersatz-motel-sqli/how-to-solve.md), and [Cyber Command admin flag](../../challenges/cyber-command-admin-flag/how-to-solve.md). For historical facts or map research, use [web investigation and OSINT](web-osint.md).

