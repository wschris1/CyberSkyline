# Conference Network Capture: how to solve

## Approach

Identify the device once, then correlate its traffic by Ethernet source address. Counting distinct destination hosts avoids mistaking repeated connection attempts for broad discovery.

## Steps

1. In Wireshark, search DNS, mDNS, DHCP, and local-discovery names for `tdavis-MAC`. Inspect those packets to determine the sender's Ethernet address; use that MAC as the stable filter for the rest of the capture.
2. For the same sender, inspect IPv4 and IPv6 source fields in outbound packets. Confirm that the addresses recur with the identified MAC.
3. Filter outbound IPv4 TCP connection attempts, excluding DNS traffic. Group by destination port and count distinct destination IPv4 addresses per port. Choose the port with the largest distinct-host count, rather than the most packets.
4. Filter outbound UDP broadcast packets from the device and inspect the discovery payloads. The repeated Drobo search traffic reveals the requested UDP destination port.
5. Filter NTP packets from the device, then read the destination IP of its time-synchronization requests. Use an authoritative address-registry or network-ownership lookup for the organization assigned the first-octet block.
6. Look up the first three bytes of the device's MAC address in the IEEE registration database or Wireshark's resolved manufacturer field. Distinguish the laptop's OUI from the manufacturers of other conference devices.

