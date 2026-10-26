# DMZ terminal: how to solve

## Approach

Treat the Kali terminal as the only authorized network vantage point. First establish the externally reachable surface, then fingerprint the highest exposed service. The later questions are a pivot: the service's filter is intended to be bypassed so that an HTTP request can reach a destination visible only from the target's network namespace.

Do not infer success from a merely different parser error. A real bypass should produce destination-dependent behavior, such as a response from the internal HTTP service. Preserve the original response headers and body while comparing probes.

## Inputs and tools

Use the live challenge terminal, `target`, and standard Kali tools such as `nmap`, `nc`/`ncat`, `curl`, and a small raw-socket script when a client normalizes the request. Do not copy the session export, terminal transcript, credentials, answer submissions, or flag into this repository.

## Steps

1. Resolve `target` and scan only the challenge host from the provided Kali machine. Record the TCP ports that are open from that vantage point, including service/version evidence where available. Treat filtered and unreachable ports separately from closed ports.
2. Connect to the highest exposed port and capture a complete response. A normal HTTP request may return an error body from the filter; keep the status, `Server` header, and body as a baseline. Confirm the version using an independent banner or service probe rather than guessing from the challenge text.
3. Model the filter before trying variants. Compare one request at a time while changing only the destination representation or request form. Use a raw TCP client for duplicate headers, absolute-form request targets, `CONNECT`, and other syntax that `curl` may rewrite. Keep each candidate tied to the exact response.
4. Test the candidate that produces a destination-dependent response against the target's loopback/admin destination and against a known closed destination. A generic `400` or the same filter `403` for both cases is not evidence of a bypass; a response from the internal service is.
5. Once the internal reachability path is proven, enumerate HTTP services from inside the target through that path, ignoring ports above 10000 as the question requires. Restrict requests to the authorized instance and stop when the additional HTTP listener is identified.
6. Retrieve the service response and verify the flag against the original response bytes. Record the port and flag privately for submission; the public guide should describe the method without reproducing either value.

Illustrative baseline (replace the port with the value established in step 1):

```bash
nmap -sT -sV --top-ports 1000 target
ncat -v target <highest-exposed-port>
```

For raw requests, build the bytes explicitly and capture the complete response. Do not assume that an HTTP status change alone means the request reached the intended upstream.

## Check your work

Repeat the baseline request before and after each candidate. Save response hashes and a short label for each probe in a private notes directory. A valid solution has all of these properties: the externally visible port count is reproducible from Kali; the service version is present in independent evidence; the bypass changes behavior according to the destination; and the internal service returns a stable HTTP response containing the submitted flag.

## Limits and next steps

The supplied investigation transcript records many equivalent address encodings and parser variants that continued to receive the same filter response. Those attempts do not establish that every request parameter or request form was tested, and they do not recover the internal port or flag. If the first matrix is inconclusive, compare the filter's exact input position and parsing path rather than submitting another unverified string. Keep the live instance and all answer-bearing evidence private.
