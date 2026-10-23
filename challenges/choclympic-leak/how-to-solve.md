# Choclympic Peaks Product Leak: how to solve

## Approach

Reconstruct the sequence of HTTP requests from the access log. Use dates, IP addresses, User-Agent strings, `file` query parameters, and response status codes together; a traversal-looking request is not by itself proof that a data file was retrieved.

## Steps

1. Parse each combined-log entry into timestamp, client IP, method, raw request target, status, byte count, and User-Agent. Retain the raw target alongside a URL-decoded copy so the final request can be reproduced exactly.
2. Group suspicious requests by client IP and calendar day. Find the client present across all three attack days, then inspect its requests in time order. Read its quoted User-Agent field verbatim.
3. Filter for requests with a `file` parameter. URL-decode a copy of each value and flag parent-directory components such as `../`, including encoded slashes. The path before the `?` identifies the endpoint that accepts the parameter.
4. On the first day, sort that client's requests by time. Take the `file` value from the earliest traversal probe, even if the server returned an error. Do not substitute a later successful probe.
5. Follow the same client through directory listing and staging-file requests on later days. A successful response to a product data file, rather than an image or directory, establishes the leaked item. Derive the slug from that file's basename without its extension.
6. Copy the successful request's path and query from the raw log, preserving the original number of `../` segments and encoding. Use that row's timestamp for the calendar date.

