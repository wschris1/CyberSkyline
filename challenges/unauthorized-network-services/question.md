# Unauthorized Network Services

A small network contains systems running services that are not allowed by IT. Use the supplied network logs to assess whether these are benign or deserve additional investigation and forensics. The field labels are not descriptive, but they are consistent across the logs.

The supplied artifact is `pi_ub2004_64.tar.gz`, containing hourly network logs. Obtain the original archive separately; it is not stored in this repository.

| Question | Points |
| --- | ---: |
| Q1. There is an unencrypted web server on this network. Based on the first word in the URI's path component, what service is it running? | 5 |
| Q2. On what IPv4 address is this service running? | 5 |
| Q3. What external IPv4 address is providing NTP services to this network? | 10 |
| Q4. Based on the IP address from Q3, what Linux variant is running on `10.0.0.238`? | 10 |
| Q5. What web browser software is being used on `10.0.0.111`? | 10 |
| Q6. The logs show checks for firmware updates over an encrypted connection. What is the DNS name for that server? | 10 |
| Q7. What device, other than the MacBook, advertises itself as having Remote Audio Output Protocol available over TCP? Use the format `model, product`. | 15 |
| Q8. Exactly one system wants to keep using a DNS name, rather than just a hostname. Of what organization is that name a part? Use the format `domain.tld`. | 10 |
| Q9. What is the MAC address of a network infrastructure device that requested a DHCP lease? | 10 |
| Q10. Zeek flagged an anomaly on the very first exchange with a networked device. What Microsoft protocol suite does the exposed API on the device belong to? | 15 |
