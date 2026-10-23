# YARA Secret Hunt: how to solve

## Approach

Scan the entire project recursively and distinguish a YARA rule match from an individual string match. A rule is reported once for each matching file, while `-s` also prints every matching string and its identifier. One file can therefore contribute one rule match and several string matches.

## Steps

1. Locate the rule, the target directory, and the named configuration file:

   ```bash
   find /home/analyst -type f \( -name 'scan.yara' -o -name 'database.ini' \) -print
   ```

2. Run the rule recursively without string details. This produces one line for each rule-and-file match, which is the quantity requested by the first question:

   ```bash
   yara -r /home/analyst/scan.yara /home/analyst/verify
   ```

   To count those lines mechanically, append `| wc -l`.

3. Run a detailed scan to display matching string identifiers and offsets:

   ```bash
   yara -r -s /home/analyst/scan.yara /home/analyst/verify
   ```

   The text after each offset begins with the matching `$identifier`. Do not publish the text following the identifier because it may contain the exposed secret. A redacted view can be produced with:

   ```bash
   yara -r -s /home/analyst/scan.yara /home/analyst/verify |
     sed -E 's/^([[:space:]]*0x[[:xdigit:]]+:\$[^:]+):.*/\1: [redacted]/'
   ```

4. Isolate the scan to `database.ini` and read the identifier from its string-match line:

   ```bash
   yara -s /home/analyst/scan.yara /home/analyst/verify/database.ini
   ```

5. For the number of pattern types, collect the `$identifier` fields from the full detailed scan, remove duplicates with `sort -u`, and count the remaining lines. Repeated hits from the same identifier count as one type.
6. Read the `strings` section of the rule:

   ```bash
   sed -n '/strings:/,/condition:/p' /home/analyst/scan.yara
   ```

   Compare every declared identifier with the unique identifiers in the scan results. The declared identifier absent from the results is the unmatched pattern.

## Check your work

The detailed output can contain more string lines than the rule-only output contains file lines. Verify that every identifier counted as a pattern type appears at least once, and that the pattern selected as unmatched is declared in the rule but absent from every scan result.
