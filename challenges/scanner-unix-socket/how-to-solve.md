# Scanner Unix socket: how to solve

## Approach

Treat the SSH account as a constrained foothold. Begin with local process and filesystem discovery, then determine which process owns the unusual Unix socket. The socket is the intended trust-boundary mistake: identify its protocol and use the least invasive local client needed to reach the scanner backend.

## Inputs and tools

Use the challenge-provided SSH endpoint and credentials, `ps`, `/proc`, `find`, `ss` or `lsof` if available, and the client implied by the socket's protocol. Do not place credentials, private keys, command transcripts, or flags in this repository.

## Steps

1. Confirm the account, hostname, and privilege boundaries. Enumerate processes and their command lines, then inspect open file descriptors and Unix-domain listeners.
2. Search likely runtime directories and `/proc/net/unix`, correlating each socket inode with the owning process. Record the full path exactly, including directory and filename.
3. Inspect the owning executable's help, environment, and nearby configuration without modifying the host. Determine whether the socket speaks HTTP, a line protocol, or a scanner-specific protocol.
4. Query the socket locally with the smallest safe request. Follow the application's response and any documented scanner functionality to reach the protected data.
5. Verify the final flag through a second read or a stable response, then submit the socket path and flag privately in the challenge platform.

## Check your work

The socket path should be supported by both the listener table and the owning process's file-descriptor mapping. A successful request should be reproducible in a fresh shell and should come from the local socket rather than an unrelated network service.

## Limits and next steps

The available conversation record contains the prompt but not a verified socket path or flag. Those values are intentionally omitted here. If the process list is sparse, inspect service managers, inherited file descriptors, and per-process working directories before escalating privileges.
