# Live Relay Cipher

Liber8tion seems to have built a custom cipher for its internal relay communications. A live relay node streams the encrypted traffic.

```sh
nc services.cityinthe.cloud 4444
```

## Q1 — 10 points

What type of cipher generates the keystream? Both the full form and abbreviation are accepted.

## Q2 — 85 points

What is the flag?

## Protocol information supplied by the service

```text
=== LIBER8TION RELAY INTERCEPT ===
[LiberStream v2.1 - live traffic tap]
[TAPMAP R0=0x20009 R1=0x80027 R2=0x800021]
[MODE ARB-STEP]
[INIT zero regs; key bits, then 32 seq bits, mixed in 1 bit/clock, all regs]
[FRAME "L8" | type:u8 | seq:u32be | plen:u8 | body:32]
[TYPE 01=STATUS 02=SECURE]
--- BEGIN BINARY STREAM ---
```

Capture the binary stream locally as `relay.bin`. The session capture is excluded from this repository.
