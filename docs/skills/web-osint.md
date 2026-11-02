# Skill: web investigation and OSINT

## Web evidence first

Record the exact authorized URL, allowed protocols, rate limits, and restrictions on automated requests. A challenge permitting educated, limited fuzzing does not authorize a random directory brute-force job. Keep requests deliberate and record the result of each hypothesis.

Inspect a normal request's status, headers, cookies, body, links, forms, and browser-visible behavior. Source code or configuration supplied with the challenge is stronger evidence for internals than a guessed framework based on appearance. Preserve the raw request and response beside any parsed or decoded copies.

A generic request template is:

```text
curl -i --connect-timeout 5 --max-time 15 OBSERVED_URL
```

Replace the URL from current evidence. Check a redirect's destination and scope before following it. Headers may carry clues that the rendered page omits. Distinguish header names from values and advertised server software from verified backend language. A `200` response can be a login page or application error; inspect the body and session context.

Change one relevant variable per test: path, parameter, encoding, content type, or account context. Compare with a baseline. Preserve the original encoding and decode a copy when analyzing traversal-like inputs; do not lose the exact request the question asks for. Stop and reassess when throttling or an explicit limit is reached.

## OSINT with time and identity controls

Write down the entity and date being asked about. A current owner, flag state, domain, conference name, or company record may differ from the historical answer. Distinguish founding year, first event, renamed event, and the source's publication date.

Prefer primary sources: official documentation, registries, event archives, incident reports, maps, and first-party project records. Search snippets are leads; open the underlying source and verify the relevant passage. Retain source URL, date, quoted evidence, and your inference privately. Resolve contradictions rather than averaging or selecting the most repeated claim.

For identity and location matches, combine independent attributes. A shared name, broad region, IP address, or manufacturer prefix alone may be ambiguous. Correlate date, coordinates, model/revision, identifier, and context. Do not infer nationality, ownership, or a person's identity from an address geolocation alone.

## Exactness checks

| Question type | Common mismatch |
| --- | --- |
| Hostname / domain | Full URL, path, port, or subdomain accidentally included or removed |
| Registrable base domain | Taking the last two labels fails for multi-label public suffixes |
| Historical operator | Current owner substituted for operator at the incident date |
| Distance | Trail/road distance substituted for great-circle distance, or units changed |
| Institution identifier | Prefix treated as globally unique without corroboration |
| Count | Events substituted for distinct entities or repeated records counted twice |
| Full request target | URL-decoding or normalizing away characters the prompt requires |

Keep calculations reproducible and round at the final step. State uncertainties when the evidence does not uniquely identify the entity. Link evidence supporting the actual claim; an official-looking page that does not contain the claim is not verification.

Related guides: [community research](../../challenges/cybersecurity-community/how-to-solve.md), [device revisions](../../challenges/device-default-passwords/how-to-solve.md), [map calculations](../../challenges/map-itinerary/how-to-solve.md), [vessel history](../../challenges/vessel-tracking/how-to-solve.md), and [web authentication configuration](../../challenges/nginx-basic-auth/how-to-solve.md).

Reference: [curl manual](https://curl.se/docs/manpage.html). Use current official records for facts that can change, and dated archives for historical questions.

## Repository helpers

For captured evidence, use the [HTTP and URL helpers](../../tools/README.md#saved-http-and-url-evidence). These tools inspect local text/bytes and do not follow redirects or request a remote page.
