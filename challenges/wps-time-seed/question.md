# Time-Seeded WPS Handshake

The supplied `capture (1).pcap` contains a WPS exchange, and `registrar_dhpriv (1).txt` contains the registrar's Diffie-Hellman private key. The AP uses a weak PRNG seeded with Unix time for WPS nonce generation. Recover the AP's MAC address, manufacturer, model, WPS DH group bit length, and PIN.

The capture and private key are supplied challenge artifacts and are not stored in this repository.

