# Browser History Investigation: how to solve

## Approach

Firefox stores visited URLs in `moz_places` and individual visits in `moz_historyvisits`. Join the tables using `moz_historyvisits.place_id = moz_places.id`, convert Firefox's microsecond Unix timestamps, and order the result by `visit_date`. The resulting timeline supplies most of the evidence; focused queries make the counts and time calculations reproducible.

## Steps

1. Locate the exported database. On a minimal box without `find`, recursively list the working directory:

   ```bash
   ls -laR .
   ```

2. Confirm that it is a Firefox Places database and inspect the relevant schemas:

   ```bash
   sqlite3 places.sqlite ".tables"
   sqlite3 places.sqlite ".schema moz_places"
   sqlite3 places.sqlite ".schema moz_historyvisits"
   ```

3. Build the complete timeline. Firefox records `visit_date` as microseconds since the Unix epoch, so divide by one million before using SQLite's `datetime` function:

   ```bash
   sqlite3 -header -column places.sqlite \
     "SELECT datetime(v.visit_date/1000000,'unixepoch') AS time_utc,
             p.url,
             p.title
        FROM moz_historyvisits AS v
        JOIN moz_places AS p ON p.id = v.place_id
       ORDER BY v.visit_date;"
   ```

4. Identify the first and final searches by filtering the ordered timeline for the search engine's search-path URLs. Read the `q` query parameter, converting `+` to spaces and percent-decoding any escaped characters:

   ```bash
   sqlite3 -header -column places.sqlite \
     "SELECT datetime(v.visit_date/1000000,'unixepoch') AS time_utc, p.url
        FROM moz_historyvisits AS v
        JOIN moz_places AS p ON p.id = v.place_id
       WHERE p.url LIKE '%/search?%'
       ORDER BY v.visit_date;"
   ```

5. Search the timeline for a download page and use its URL and title to infer the software. Search separately for `github.com`, `support.`, `reddit.com`, and `benchmark` to isolate the repository, support site, later subreddit, and benchmark resource:

   ```bash
   sqlite3 -header -column places.sqlite \
     "SELECT datetime(v.visit_date/1000000,'unixepoch') AS time_utc, p.url, p.title
        FROM moz_historyvisits AS v
        JOIN moz_places AS p ON p.id = v.place_id
       WHERE p.url LIKE '%download%'
          OR p.url LIKE '%github.com%'
          OR p.url LIKE '%support.%'
          OR p.url LIKE '%reddit.com%'
          OR p.url LIKE '%benchmark%'
       ORDER BY v.visit_date;"
   ```

   Use the timestamps to ensure the chosen subreddit occurs after the support-domain visit.

6. Calculate the elapsed time directly from the raw microsecond timestamps:

   ```bash
   sqlite3 -header -column places.sqlite \
     "SELECT (MAX(visit_date)-MIN(visit_date))/60000000.0 AS elapsed_minutes
        FROM moz_historyvisits;"
   ```

   Apply the challenge's requested whole-minute precision consistently rather than counting clock-minute labels.

7. Extract hosts from all visited URLs, then normalize them to registrable base domains. Remove prefixes such as `www.` and collapse meaningful subdomains such as `support.` into their parent domain. Count each normalized domain once. For this dataset, the hosts can first be listed with:

   ```bash
   sqlite3 places.sqlite "SELECT DISTINCT url FROM moz_places WHERE url LIKE 'http%';"
   ```

   Do not blindly take the last two labels for arbitrary real-world domains because suffixes such as `co.uk` require a public-suffix-aware parser.

8. Query the earliest raw timestamp and its UTC conversion for the calendar response:

   ```bash
   sqlite3 -header -column places.sqlite \
     "SELECT MIN(visit_date) AS first_raw,
             datetime(MIN(visit_date)/1000000,'unixepoch') AS first_utc
        FROM moz_historyvisits;"
   ```

   Enter the result only to the minute, as requested. Preserve UTC unless the challenge explicitly specifies another timezone.

## Check your work

Confirm that the first and last records used for the elapsed-time calculation match the endpoints of the ordered timeline. Every base domain should appear only once after normalization, even when both a root host and one or more subdomains were visited. Keep the inferred software, repository, domains, queries, timestamp, and counts in the CTF platform rather than this repository.
