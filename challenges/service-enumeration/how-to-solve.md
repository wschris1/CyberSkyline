# Service Enumeration: how to solve

## Approach

Discover the open TCP ports first, then inspect the relevant protocols directly. Save exact responses privately before interpreting the values. The complete reusable workflow is in [service enumeration](../../docs/skills/service-enumeration.md).

## Steps

1. In the challenge's scanner terminal, run:

   ```sh
   nmap -p- --open target
   ```

   Wait for completion and retain the port table. If an earlier `--version-all` scan appears stuck at a service-detection percentage, the increasing estimate is not proof of a stalled port scan. A separate port-only inventory can establish what actually listens.

2. Use lightweight version detection on the observed ports. Replace the uppercase list in this template with those ports:

   ```text
   nmap -sV --version-light --script=banner -p DISCOVERED_PORTS target
   ```

   Confirm the insecure shell protocol from a response or service detection. Do not promote the conventional SERVICE label from a bare scan into confirmed evidence.

3. Identify the numerically lowest open TCP port and capture its raw greeting. A compatible Netcat client can use `nc -w 5 target PORT`, with the actual port substituted. Preserve the complete banner. Separate any protocol prefix from the product/version and distribution suffix when interpreting the wording of the question.

4. Inspect protocol greetings for a service-advertised hostname. Compare it with any reverse-DNS name, but keep those sources separate. The infrastructure's generated container name need not be the hostname requested by the question.

5. For an observed HTTP endpoint, request the full response with curl's `-i` option. Inspect all headers as well as the page body. A custom response header can contain the requested value even when the page itself is a generic welcome message.

6. Record each question's source and exact value privately. Preserve case, punctuation, and the full version suffix. Retain necessary evidence before completing an instance that will disappear.

## Check your work

Make a private table mapping port, detected protocol, raw response, and question. Confirm that the version came from the lowest **TCP** port and that the FQDN came from the relevant service. This guide records a reproducible method, not a set of values to reuse across instances. No final response or token is published here.
