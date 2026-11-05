"""Fixed verification adapters. No shell, dynamic commands, eval, network or artifact execution."""

import hashlib
from datetime import datetime
import json
from pathlib import Path
import re
import sys
import zipfile

# -I ignores inherited import paths. Only this installed, hash-pinned repository is added.
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from tools import artifact_inventory, decode_value, pcap_summary, http_response_inspect, timestamp_convert, image_metadata, strings_extract

LIMIT = 64*1024*1024


def result(outcome, method, evidence):
    return dict(outcome=outcome,method=method,evidence=evidence)


def compare(expected, answer, method, evidence):
    return result('Verified correct' if expected == answer else 'Verified incorrect',method,evidence)


def choose_file(files, question):
    named = [f for f in files if f['name'].casefold() in question.casefold()]
    selected = named if named else files
    return selected[0] if len(selected) == 1 else None


def metadata_check(path, plain, answer):
    creation = re.fullmatch(r'when was (?:the |this )?(?:image|photo|photograph|picture) (?:created|taken)\??'
                            r'(?:[. ]+round down to the nearest minute)?', plain)
    if not creation:
        return None
    report = image_metadata.inspect(path.read_bytes())
    tags = [t for t in report['tags'] if t['tag'] in ('DateTimeOriginal', 'DateTimeDigitized')]
    if not tags:
        return result('Inconclusive', 'tools/image_metadata.py',
                      'No EXIF original/digitized timestamp exists. Modification/download dates are not creation evidence.')
    minute = 'round down to the nearest minute' in plain
    values = [datetime.strptime(t['value'], '%Y:%m:%d %H:%M:%S') for t in tags]
    values = [v.replace(second=0, microsecond=0) if minute else v for v in values]
    if len(set(values)) != 1:
        return result('Inconclusive', 'tools/image_metadata.py',
                      'EXIF original and digitized timestamps conflict; the intended creation field is ambiguous.')
    expected = values[0].strftime('%Y-%m-%d %H:%M' if minute else '%Y-%m-%d %H:%M:%S')
    try:
        datetime.strptime(answer, '%Y-%m-%d %H:%M' if minute else '%Y-%m-%d %H:%M:%S')
    except ValueError:
        return result('Inconclusive', 'tools/image_metadata.py',
                      'Use YYYY-MM-DD HH:MM' + ('.' if minute else ':SS.') +
                      ' The EXIF value has no requested timezone conversion; answer whitespace is preserved.')
    basis = ', '.join(f"{t['tag']} at byte {t['offset']}" for t in tags)
    return compare(expected, answer, 'tools/image_metadata.py',
                   f'Read {basis} from the original file' + (' and rounded down to the minute' if minute else '') +
                   '. Compared the recorded local camera time without assuming a timezone; metadata is not proof of clock accuracy.')


def validate_files(data):
    root = Path(data['root']).resolve()
    for f in data['files']:
        p = Path(f['path'])
        if p.is_symlink() or not p.resolve().is_relative_to(root) or not p.is_file() or p.stat().st_size > 2*1024**3:
            raise ValueError('Evidence file unavailable or outside the verification limit')
        if artifact_inventory.sha256_file(p) != f['sha256']:
            raise ValueError('Evidence file changed')


def inspect_evidence(data):
    """Allowlisted, read-only operations. AI never supplies paths, commands or an answer."""
    validate_files(data)
    request = data['inspect']
    if not isinstance(request, dict) or set(request) != {'file_id', 'operation'}:
        raise ValueError('Invalid tool arguments')
    index = request['file_id']
    if type(index) is not int or not 0 <= index < len(data['files']):
        raise ValueError('Unknown evidence file')
    item = data['files'][index]
    path = Path(item['path'])
    operation = request['operation']
    if path.stat().st_size > LIMIT and operation not in ('file_facts','text','strings'):
        return dict(error='This operation is limited to 64 MiB on the bot worker. The larger file remains cached; file facts and bounded text/strings previews are available.')
    if operation == 'verify':
        # Preserve the actual question and exact proposed answer. Restrict the
        # evidence file only when the prompt explicitly names it or it is unique.
        selected = choose_file(data['files'], data['question'] + '\n' + data['instructions'])
        if selected != item:
            return dict(error='The original question does not unambiguously select this file.')
        return check({**data, 'files': [item]})
    if operation == 'metadata':
        return image_metadata.inspect(path.read_bytes())
    if operation == 'file_facts':
        return dict(size=path.stat().st_size, sha256=item['sha256'], kind=artifact_inventory.identify(path))
    if operation in ('text', 'strings'):
        with path.open('rb') as source:
            raw = source.read(8193)
        if operation == 'text':
            return dict(text=raw[:8192].decode('utf-8', errors='replace'),
                        truncated=len(raw)>8192, offset=0, bytes_read=min(len(raw),8192))
        report = strings_extract.extract(raw[:8192], minimum=4, limit=40)
        report['truncated'] = report['truncated'] or len(raw)>8192
        return report
    if operation == 'pcap_summary':
        return pcap_summary.summarize(path.read_bytes())
    if operation == 'http_response':
        report = http_response_inspect.inspect(path.read_bytes())
        # Never forward cookies or authentication headers to the AI.
        return {k:v for k,v in report.items() if k not in ('headers','body','raw')}
    raise ValueError('Unsupported evidence operation')


def check(data):
    question,instructions,answer = data['question'],data['instructions'],data['answer']
    evidence_text = question + '\n' + instructions
    q = question.casefold()
    files = data['files']
    try:
        validate_files(data)
    except (OSError, ValueError):
        return result('Verification error','evidence files','A cached file changed or is unavailable; refresh the source before verifying.')
    if any(Path(f['path']).stat().st_size > LIMIT for f in files):
        return result('Inconclusive','large evidence file',
            'The original file is cached, but deterministic verification is limited to 64 MiB per file on this worker. AI can inspect bounded file facts/text/strings; full memory-image analysis needs an external analysis runtime.')
    selected = choose_file(files,question)
    path = Path(selected['path']) if selected else None
    # These adapters deliberately recognize narrow question shapes. A keyword alone
    # cannot prove that a whole-file measurement answers a filtered/derived question.
    plain = re.sub(r'^\s*\**q\d+\s*[-–:]\s*\d+\s*points?\**\s*', '', q)
    plain = re.sub(r'\s+', ' ', plain).strip().rstrip('?.')
    if path:
        metadata = metadata_check(path, plain, answer)
        if metadata:
            return metadata
    supplied = r'(?:(?:the|this|supplied|provided|original|attached) )?(?:file|capture|archive|packet capture)'
    if selected:
        supplied += r'|`?' + re.escape(selected['name'].casefold()) + r'`?'
    supplied = '(?:' + supplied + ')'
    compound = re.search(r'\b(then|reverse|reversed|xor|first|last|substring|uppercase|lowercase|concatenate|decompress)\b',evidence_text,re.I)
    password_request = re.fullmatch(r'(?:what is (?:the )?(?:zip )?password(?: (?:for|of) [\w@` .-]+)?|'
                                   r'(?:recover|find) (?:the )?(?:zip )?password)',plain)

    # A candidate is checked against one explicitly identified unsalted digest, never guessed from length alone.
    algorithms = [(label,canonical) for label,canonical in [('md5','md5'),('sha-1','sha1'),('sha1','sha1'),
                  ('sha-256','sha256'),('sha256','sha256'),('sha-512','sha512'),('sha512','sha512')]
                  if re.search(r'\b'+re.escape(label)+r'\b',evidence_text,re.I)]
    algorithms = sorted({a[1] for a in algorithms})
    if password_request and not compound and len(algorithms)==1 and re.search(r'\bunsalted\b',evidence_text,re.I):
        algo = algorithms[0]
        size = hashlib.new(algo).digest_size*2
        source = evidence_text
        if path and path.stat().st_size <= 65536:
            source += '\n'+path.read_text(encoding='utf-8')
        hashes = set(re.findall(r'(?i)(?<![a-f0-9])[a-f0-9]{'+str(size)+r'}(?![a-f0-9])',source))
        if len(hashes)==1:
            matched = hashlib.new(algo,answer.encode('utf-8')).hexdigest() == next(iter(hashes)).lower()
            return result('Verified correct' if matched else 'Verified incorrect','unsalted '+algo,
                          'Hashed the exact proposed UTF-8 bytes and compared with the single supplied digest.')
    zip_password = 'zip' in plain or re.search(r'\b(?:zip password|password (?:for|of|to) (?:the )?(?:encrypted )?zip)\b',instructions,re.I)
    if password_request and not compound and zip_password and path and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            entries = [i for i in archive.infolist() if not i.is_dir()]
            if not entries or not all(i.flag_bits & 1 for i in entries):
                return result('Inconclusive','ZIP password','The archive does not provide a fully encrypted password check.')
            if sum(i.file_size for i in entries)>LIMIT or len(entries)>1000:
                return result('Verification error','ZIP password','Archive exceeds the bounded verification size.')
            try:
                for info in entries:
                    with archive.open(info,pwd=answer.encode('utf-8')) as source:
                        size=0
                        while chunk:=source.read(65536):
                            size+=len(chunk)
                            if size>LIMIT:
                                raise ValueError('size limit')
            except RuntimeError as exc:
                if 'Bad password' in str(exc):
                    return result('Verified incorrect','ZIP password','The encrypted ZIP password check rejected the exact proposed bytes.')
                raise
            return result('Verified correct','ZIP password','Decrypted all encrypted members and verified their CRCs without extracting or executing them.')

    if re.search(r'\bdecode(?:d)?\b',q):
        simple_decode = re.fullmatch(r'(?:what is (?:the )?decoded (?:(?:base64|base64url|hex) )?(?:value|text|message)|'
            r'decode (?:the )?(?:(?:base64|base64url|hex) )?(?:value|text|message|input|data)(?: in '+supplied+r')?)',plain)
        if not simple_decode or compound:
            return result('Inconclusive','decode_value','Only a direct decoding question is supported; derived or multi-step questions need another adapter.')
        encodings = [v for v in ('base64','base64url','hex') if re.search(r'\b'+v+r'\b',evidence_text,re.I)]
        if len(encodings)==1:
            if path and path.stat().st_size<=65536:
                encoded=path.read_text(encoding='utf-8')
            else:
                values=re.findall(r'(?s)```(?:text)?\n(.*?)\n```|(?<!`)`([^`\n]+)`(?!`)',evidence_text)
                values=[a or b for a,b in values]
                if len(values)!=1:
                    return result('Inconclusive','decode_value','Choose a single encoded input file or include one explicit encoded value.')
                encoded=values[0]
            decoded,round_trip=decode_value.decode(encoded,encodings[0])
            if not round_trip:
                return result('Inconclusive','decode_value','The representation did not pass the tool’s round-trip check.')
            return compare(decoded,answer.encode('utf-8'),'tools/decode_value.py',
                           f'Decoded {encodings[0]} and checked the round trip; compared exact bytes, including whitespace.')
    if path and re.search(r'\b(?:sha-?256|sha-?1|md5|sha-?512)\b.*\b(?:hash|digest|checksum)\b|\b(?:hash|digest|checksum)\b.*\b(?:sha-?256|sha-?1|md5|sha-?512)\b',q):
        if compound or not re.fullmatch(r'what is (?:the )?(?:sha-?256|sha-?1|md5|sha-?512) (?:hash|digest|checksum)(?: of '+supplied+r')?',plain):
            return result('Inconclusive','file digest','Only an explicit whole-file digest question is supported.')
        if len(algorithms)==1:
            algo=algorithms[0]
            actual=artifact_inventory.sha256_file(path) if algo=='sha256' else hashlib.new(algo,path.read_bytes()).hexdigest()
            return compare(actual,answer.casefold(),'tools/artifact_inventory.py + '+algo,
                           'Recomputed the file digest; hexadecimal letter case does not affect the digest.')
    if path and re.search(r'\b(?:file size|size of (?:the|this) file|how many bytes)\b',q) and 'byte' in q:
        if compound or not re.fullmatch(r'(?:what is (?:the )?file size in bytes|what is (?:the )?size of '+supplied+r' in bytes|how many bytes (?:are in|is) '+supplied+r')',plain):
            return result('Inconclusive','file size','Only the complete original file size in bytes is supported.')
        actual=str(path.stat().st_size)
        return compare(actual,answer,'tools/artifact_inventory.py',f'Measured the original file: {actual} bytes; decimal bytes only.')
    if path and re.search(r'\b(?:how many|number of|total)\b.*\bpackets\b',q):
        # More specific protocol, direction or time-window questions need a richer adapter.
        if compound or not re.fullmatch(r'(?:how many packets are in '+supplied+r'|what is the (?:total )?number of packets in '+supplied+r')',plain):
            return result('Inconclusive','tools/pcap_summary.py','This question needs packet filtering that this metadata adapter does not implement.')
        report=pcap_summary.summarize(path.read_bytes())
        if report['packet_limit_reached'] or report['warnings']:
            return result('Inconclusive','tools/pcap_summary.py','Capture coverage or warnings prevent a conclusive count.')
        return compare(str(report['packets_scanned']),answer,'tools/pcap_summary.py',
                       f"Parsed the entire classic PCAP: {report['packets_scanned']} packet records.")
    if path and re.search(r'\bhttp\b',evidence_text,re.I) and re.search(r'\bstatus code\b',q):
        if compound or not re.fullmatch(r'what (?:is the )?(?:final )?http status code(?: is shown| of the (?:saved|final) response)?',plain):
            return result('Inconclusive','HTTP status','Only the final status of one saved HTTP response is supported.')
        report=http_response_inspect.inspect(path.read_bytes())
        return compare(str(report['status']),answer,'tools/http_response_inspect.py','Parsed the final HTTP/1.x response status line.')
    if re.search(r'\b(?:convert|timestamp|date|time)\b',q):
        formats=[f for f in timestamp_convert.FORMATS if f in evidence_text]
        numbers=re.findall(r'(?<!\w)`(-?\d+(?:\.\d+)?)`',evidence_text)
        clock_question = re.sub(r'`-?\d+(?:\.\d+)?`','<value>',plain)
        simple_clock = re.fullmatch(r'convert (?:the |this )?(?:<value> )?(?:(?:unix-s|unix-ms|unix-us|unix-ns|webkit-us) )?timestamp(?: <value>)? to iso(?: 8601)? utc(?: (?:with|using) six fractional digits)?',clock_question)
        if not compound and simple_clock and len(formats)==len(numbers)==1:
            actual=timestamp_convert.convert(numbers[0],formats[0])
            return compare(actual,answer,'tools/timestamp_convert.py','Used the explicit epoch/unit and compared ISO UTC with six fractional digits.')
    return result('Inconclusive','supported evidence adapters',
                  'No unambiguous supported check links this question to available evidence. Format alone cannot establish correctness.')


def main():
    try:
        if sys.platform!='win32':
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(8,8))
            resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
            resource.setrlimit(resource.RLIMIT_FSIZE,(1024*1024,1024*1024))
            resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))
        raw=sys.stdin.buffer.read(1024*1024+1)
        if len(raw)>1024*1024:
            raise ValueError('input too large')
        data = json.loads(raw)
        output = inspect_evidence(data) if 'inspect' in data else check(data)
    except Exception as exc:
        output=result('Verification error','evidence adapter',f'The tool could not complete ({type(exc).__name__}); no correctness conclusion was drawn.')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':
    main()
