# Web security source review: how to solve

## Approach

Read the supplied application source before interacting with the live instance. Map routes, template rendering, cookie creation, bot behavior, and any cross-origin or request-validation settings. Use the source to form a minimal test for each question, then verify the behavior against the authorized challenge host.

## Inputs and tools

The challenge provides an `app.py`-style source file and a temporary web instance. Use a local editor, Python's standard-library inspection tools, and a browser or `curl` for requests to that instance. Do not publish the source, cookies, flags, or challenge URL containing a live token.

## Steps

1. Inventory every route and identify where `/login` reads credentials, constructs a response, and renders or redirects. Record the exact sink and its input source privately.
2. Classify the `/login` weakness with the CWE catalog. Choose an ID whose definition matches the observed code path; do not submit a generic web label without tying it to the source.
3. Trace the bot workflow and the `https://callback/` request. Inspect the cookie name, attributes, and value at the callback boundary. Treat browser developer-tool output as response-bearing evidence.
4. Search templates and response builders for values rendered without the application's sanitization or escaping helper. Confirm the route experimentally with a harmless marker, then record only the path privately.
5. Read the `/admin` handler and determine the condition that causes its flag-bearing response. Verify the response after the application is ready and preserve the flag outside the repository.

## Check your work

For each answer, maintain two independent observations: the source line or route that predicts the behavior and the live response that confirms it. Use a fresh browser context when checking cookies so an old session cannot mask the result.

## Limits and next steps

The available conversation summary identifies the questions but does not include the source file or verified responses. This guide therefore records the reproducible method without claiming any CWE, path, cookie value, or flag.
