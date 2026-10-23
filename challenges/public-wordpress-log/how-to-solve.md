# Public WordPress Access Log: how to solve

## Approach

Treat the file as CEF-formatted HTTP events. Read the CEF header separately from fields such as `src`, `request`, `proto`, and `out`; then correlate events by path, response code, and client IP.

## Steps

1. Read the CEF product/version fields at the start of a row for the web server version. To identify WordPress, inspect versioned WordPress asset requests and corroborate the version across more than one core asset where possible.
2. Search the `request=` field for the access-log filename. The parent path of those public requests is the exposed log directory. Report that directory in the requested slash-delimited format.
3. Compare the log-file requests. A `200` response with the large `out=` value is the complete download; record its `src` and byte count from that same row. A prior `206 Partial Content` response identifies the separate partial-download client.
4. Filter the complete-download client's other requests for thumbnail or image-resizing scripts. Parse and percent-decode the URL supplied to the script's source parameter, then extract only the external hostname requested there.
5. For the login question, locate the unusual request target containing an absolute URL. Match its complete malformed request string on the relevant date, then count distinct `src` values, not the number of rows. Keep ordinary relative-path login attempts out of the count.
6. Recheck each selected row's timestamp and status, since similar scans occur elsewhere in this long log.

