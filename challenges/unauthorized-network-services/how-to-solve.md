# Unauthorized Network Services: how to solve

## Inventory the evidence

Keep the original archive outside the repository and work on an extracted copy. List the archive before extracting it:

```bash
tar -tzf ~/pi_ub2004_64.tar.gz | head -40
tar -xzf ~/pi_ub2004_64.tar.gz -C ~
LOGDIR=~/pi_ub2004_64
head -n 3 "$LOGDIR"/http.*.log
```

The files are JSON Lines, with one event per line. Shell globs cover all hourly rotations, so a missing `find` command does not prevent analysis. Run each command separately when pasting into the terminal.

Inspect several records from each log type and infer fields from recognizable IP addresses, ports, methods, and protocol values. Build this working map:

| Log type | Useful fields |
| --- | --- |
| Connection-oriented records | `f1`: timestamp; `f9`: connection UID; `f10`/`f11`: originator IP/port; `f12`/`f13`: responder IP/port |
| HTTP | `f79`: method; `f80`: Host; `f81`: URI; `f84`: User-Agent; `f96`: request MIME types |
| DNS | `f42`: queried name; `f46`: record type; `f54`: answers |
| TLS (`ssl`) | `f132`: server name/SNI |
| NTP | `f102`: mode |
| DHCP | `f32`: client MAC; `f33`: hostname; `f34`: client FQDN; `f35`: supplied domain; `f40`: message types |
| Anomalies (`weird`) | `f123`: anomaly name; `f9`: correlation UID |

Validate the map within each log type. A generic label can represent different protocol-specific data in different files; for example, a version field does not have the same interpretation in HTTP and TLS.

## Trace the web and time services: Q1–Q5

1. Read HTTP requests directed to local addresses on the cleartext web port. Split each URI into path components and inspect the first nonempty component. Verify the indicated application against the request context. The HTTP Host header and responder address help connect the name to the server; use the responder's IPv4 address for the address question.
2. Inspect NTP events and connections using UDP port 123. Separate client requests from server replies using NTP modes 3 and 4. Follow the local client to the external responder and check that repeated exchanges agree.
3. Search DNS logs for the responder address, substituting the address found in the previous step:

   ```bash
   NTP_SERVER_IP='replace-with-observed-address'
   grep -hF "$NTP_SERVER_IP" "$LOGDIR"/dns.*.log | head -n 5
   ```

   This search returned no matching DNS events in the supplied evidence. Continue with authoritative address/hostname records and documentation of distribution time-server defaults. Prefer evidence applicable to the capture date. A distribution-associated default supports an OS inference; it does not independently prove the installed distribution or release.
4. Filter HTTP records whose originator is the browser client named in Q5 and examine `f84`. Identify the actual browser product from the complete User-Agent. Compatibility tokens can name other browsers, so do not select the first recognizable name.

## Follow encrypted updates and service discovery: Q6–Q7

1. Inspect the TLS logs for server names associated with firmware distribution. Correlate SNI with DNS and connection records, then check the service's official documentation. SNI identifies the requested server name; it does not reveal an encrypted HTTP request path or prove which firmware was downloaded.
2. Search multicast DNS records for the advertised audio service:

   ```bash
   grep -hi '_raop._tcp' "$LOGDIR"/dns.*.log | head -n 10
   ```

3. Distinguish queries from responses. Follow PTR answers to service instances, exclude the MacBook instance, and record the other advertiser's address and friendly name. Discovery uses multicast UDP even though the advertised service uses TCP.
4. Search all DNS rotations for that instance name and inspect related TXT records:

   ```bash
   INSTANCE_NAME='replace-with-observed-instance-name'
   grep -hiF "$INSTANCE_NAME" "$LOGDIR"/dns.*.log |
     grep -iE 'TXT|model|product|am=|md=' | head -n 10
   ```

5. Extract a model identifier from the device's related advertisements and resolve it to a product using vendor documentation. Decode Zeek string escapes when needed: an escaped hexadecimal comma is punctuation within the model, rather than part of its literal spelling. Preserve both the model identifier and product name in the requested format.

## Separate DHCP names and infrastructure: Q8–Q9

Find client FQDNs that are actually populated:

```bash
grep -h '"f34":' "$LOGDIR"/dhcp.*.log |
  grep -v '"f34": "-"' | head -n 10
```

The client FQDN is distinct from the short hostname and the domain offered by the DHCP server. Remove the machine label and subordinate organizational labels as appropriate to identify the organization's domain. Verify the organization using its official site.

For the infrastructure question, restrict the evidence to clients that sent a DHCP request and deduplicate MAC/hostname pairs:

```bash
grep -h '"REQUEST"' "$LOGDIR"/dhcp.*.log |
  grep -oE '"f32": "[^"]*", "f33": "[^"]*"' | sort -u
```

This compact extraction relies on the observed field order and spacing. For differently formatted JSON, parse each line with a JSON library and select fields by name. Look up model-like hostnames in vendor documentation to distinguish network infrastructure from computers and other appliances. Take the MAC from the same client record, rather than the DHCP server's address.

## Correlate the anomaly with the API: Q10

1. Inspect all `weird` events and select the earliest timestamp numerically. Do not assume the first line of a concatenation is necessarily the earliest event.
2. Copy that event's connection UID and search for the exact UID in the HTTP and connection logs:

   ```bash
   CONNECTION_UID='replace-with-observed-uid'
   grep -hF "$CONNECTION_UID" "$LOGDIR"/http.*.log "$LOGDIR"/conn.*.log
   ```

3. Read the method, API path, User-Agent, and MIME type together. Use those indicators to locate Microsoft's API documentation, then identify the protocol suite to which the API belongs. Distinguish the API's name from the requested suite and follow the platform's expected naming format.
4. Examine connection state and packet history alongside the anomaly. Missing response packets or an incomplete handshake can reflect capture visibility. The anomaly alone does not demonstrate exploitation.

## Check your work

Keep a private evidence table linking each response to a log filename, timestamp, UID, and relevant fields. Use precise matches for correlation and check more than the first few records before drawing conclusions. Treat service identification, policy compliance, and evidence of compromise as separate judgments. Inventory and exposure checks determine which unauthorized services need follow-up; these logs alone do not establish that a device was compromised.
