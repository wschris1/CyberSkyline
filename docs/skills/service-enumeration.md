# Skill: service enumeration and banner interpretation

Use this when the task asks about listening services, versions, hostnames, or a response token. Work from the challenge's own terminal/network when `target` is an internal name. An unrelated assistant container may not resolve it.

## Discover, then identify

On the authorized scanner, first establish the open TCP ports:

```sh
nmap -p- --open target
```

Record the complete output. `-p-` covers TCP ports 1–65535 for this default TCP scan; it does not inspect UDP or port zero. `--open` filters what is displayed. A bare port scan's SERVICE column commonly comes from a port-number lookup, not a successful protocol identification.

Then scan **only the discovered ports** with service detection. The following is a template; replace the uppercase list before running:

```text
nmap -sV --version-light --script=banner -p DISCOVERED_PORTS target
```

Use a stronger probe only for a specific unresolved service. `--version-all` increases probe intensity and can be slow. A progress percentage stuck on service detection does not prove the whole scan is hung; estimates can rise while a probe waits. Inspect status, preserve useful results, and change strategy when an easier direct request can answer the question.

## Read raw responses

For a confirmed SSH or SMTP port, a direct connection may provide its greeting. On a Netcat implementation supporting this timeout syntax:

```text
nc -w 5 target DISCOVERED_PORT
```

For an observed HTTP service, fetch headers **and** body. Adapt the scheme, port, and host to the actual service:

```sh
curl -i --connect-timeout 5 --max-time 15 http://target/
```

Inspect custom headers as well as the visible page. A HEAD request is not identical to GET; a server can handle them differently. The `banner` NSE script can truncate displayed banners, so retain the raw response when exact text matters. An empty greeting does not prove a port is useless: some protocols wait for client input or require TLS negotiation.

## Interpret the question precisely

| Asked for | Preserve and compare |
| --- | --- |
| Insecure shell service | Observed protocol response or service detection; do not infer solely from a familiar port |
| Lowest TCP port | Lowest numeric **open TCP** port from the requested scope, not lowest service name or UDP port |
| Full service version | Product/version and distribution/build suffix, plus raw banner privately for reference |
| Full SSH banner | Entire greeting including the protocol prefix, if that is what the prompt requests |
| Service hostname | Hostname advertised by the relevant protocol; keep reverse-DNS/container labels separate |
| Token returned by a service | Exact response field/body bytes; preserve case and punctuation privately |

Do not treat a `Server` header as proof of the backend's implementation or an exploitable vulnerability. It is evidence of what the endpoint advertised. Validate output formatting against the question before reporting.

## Finish

Keep a private port-to-protocol-to-evidence table. Mark unresolved identifications instead of filling them from convention. Record the raw source separately from the interpreted answer. Use the [service challenge guide](../../challenges/service-enumeration/how-to-solve.md) for this workflow in question order.

References: [Nmap service detection](https://nmap.org/book/man-version-detection.html), [banner script](https://nmap.org/nsedoc/scripts/banner.html), and [curl options](https://curl.se/docs/manpage.html). Installed-tool help determines which options are available locally.

## Repository helpers

For saved HTTP evidence, use the [HTTP response inspector](../../tools/README.md#saved-http-and-url-evidence); it makes no network requests and requires explicit opt-in to print header values.
