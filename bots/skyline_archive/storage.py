"""Private, transactional archive state. No answers or binary artifacts enter Git."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import re
import sqlite3

from .core import ArchiveError, Challenge, event_location, level_and_title, parse_manifest


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def fingerprint(challenge):
    data = asdict(challenge)
    for ref in data.get('attachment_refs', ()):
        p = urlsplit(ref['url'])
        ref['url'] = urlunsplit((p.scheme,p.netloc,p.path,'',''))
    return digest(data)


class Store:
    VERSION = 2

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / 'archive.sqlite3'
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.path.chmod(0o600)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.migrate()

    def migrate(self):
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > self.VERSION:
            raise ArchiveError('Archive database is newer than this bot. Keep the newer release.')
        if version and version < self.VERSION:
            backup = sqlite3.connect(self.directory / f'archive.before-v{self.VERSION}.sqlite3')
            try:
                self.db.backup(backup)
            finally:
                backup.close()
            (self.directory / f'archive.before-v{self.VERSION}.sqlite3').chmod(0o600)
        if version < 1:
            self.db.executescript('''BEGIN IMMEDIATE;
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE challenges(
                    key TEXT PRIMARY KEY, event TEXT NOT NULL, season TEXT NOT NULL,
                    competition TEXT NOT NULL, category TEXT NOT NULL, level TEXT NOT NULL,
                    title TEXT NOT NULL, prompt TEXT NOT NULL, source TEXT NOT NULL,
                    fingerprint TEXT NOT NULL, synced_fingerprint TEXT, updated TEXT NOT NULL);
                CREATE TABLE questions(
                    key TEXT PRIMARY KEY, challenge_key TEXT NOT NULL REFERENCES challenges(key),
                    source_id TEXT NOT NULL, number INTEGER NOT NULL, text TEXT NOT NULL,
                    points INTEGER, channel_id INTEGER, message_id INTEGER, thread_id INTEGER,
                    github_path TEXT, UNIQUE(challenge_key, source_id));
                CREATE TABLE mappings(kind TEXT NOT NULL, scope TEXT NOT NULL, discord_id INTEGER NOT NULL,
                    PRIMARY KEY(kind, scope));
                CREATE TABLE posts(key TEXT PRIMARY KEY, channel_id INTEGER NOT NULL,
                    message_id INTEGER, fingerprint TEXT, state TEXT NOT NULL, created TEXT NOT NULL);
                CREATE TABLE attachments(key TEXT PRIMARY KEY, challenge_key TEXT NOT NULL REFERENCES challenges(key),
                    name TEXT NOT NULL, source TEXT NOT NULL, status TEXT NOT NULL, path TEXT,
                    size INTEGER, sha256 TEXT, etag TEXT, modified TEXT, message_id INTEGER,
                    channel_id INTEGER, error TEXT, updated TEXT NOT NULL);
                CREATE TABLE scans(id INTEGER PRIMARY KEY, state TEXT NOT NULL, preview INTEGER NOT NULL,
                    scope TEXT NOT NULL, progress TEXT NOT NULL, channel_id INTEGER, message_id INTEGER,
                    started TEXT NOT NULL, finished TEXT);
                CREATE TABLE verifications(id INTEGER PRIMARY KEY, question_key TEXT NOT NULL REFERENCES questions(key),
                    answer TEXT NOT NULL, user_id INTEGER NOT NULL, created TEXT NOT NULL,
                    method TEXT NOT NULL, outcome TEXT NOT NULL, evidence TEXT NOT NULL);
                CREATE INDEX question_threads ON questions(thread_id);
                CREATE INDEX question_channels ON questions(channel_id);
                PRAGMA user_version=1;
                COMMIT;''')
        if version < 2:
            self.db.executescript('''BEGIN IMMEDIATE;
                CREATE VIRTUAL TABLE question_search USING fts5(question_key UNINDEXED, title, text);
                INSERT INTO question_search SELECT q.key,c.title,q.text FROM questions q
                    JOIN challenges c ON c.key=q.challenge_key;
                CREATE TRIGGER question_search_insert AFTER INSERT ON questions BEGIN
                    INSERT INTO question_search VALUES(new.key,
                        (SELECT title FROM challenges WHERE key=new.challenge_key),new.text); END;
                CREATE TRIGGER question_search_update AFTER UPDATE OF text ON questions BEGIN
                    DELETE FROM question_search WHERE question_key=old.key;
                    INSERT INTO question_search VALUES(new.key,
                        (SELECT title FROM challenges WHERE key=new.challenge_key),new.text); END;
                CREATE TRIGGER challenge_search_title AFTER UPDATE OF title ON challenges BEGIN
                    UPDATE question_search SET title=new.title WHERE question_key IN
                        (SELECT key FROM questions WHERE challenge_key=new.key); END;
                PRAGMA user_version=2;
                COMMIT;''')

    @contextmanager
    def transaction(self):
        with self.db:
            yield

    def rows(self, sql, params=()):
        return [dict(r) for r in self.db.execute(sql, params)]

    def one(self, sql, params=()):
        rows = self.rows(sql, params)
        return rows[0] if rows else None

    def get(self, key, default=None, table='meta'):
        if table not in ('meta', 'settings'):
            raise ValueError('Invalid key/value table')
        row = self.one(f'SELECT value FROM {table} WHERE key=?', (key,))
        return json.loads(row['value']) if row else default

    def put(self, key, value, table='meta'):
        if table not in ('meta', 'settings'):
            raise ValueError('Invalid key/value table')
        with self.db:
            self.db.execute(f'INSERT INTO {table} VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                            (key, json.dumps(value)))

    def save_settings(self, values):
        with self.db:
            self.db.executemany('INSERT INTO settings VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                                [(k, json.dumps(v)) for k, v in values.items()])

    def mapping(self, kind, scope):
        row = self.one('SELECT discord_id FROM mappings WHERE kind=? AND scope=?', (kind, scope))
        return row['discord_id'] if row else None

    def map(self, kind, scope, discord_id):
        with self.db:
            self.db.execute('INSERT INTO mappings VALUES(?,?,?) ON CONFLICT(kind,scope) DO UPDATE SET discord_id=excluded.discord_id',
                            (kind, scope, discord_id))

    def upsert_challenge(self, c):
        season, competition = event_location(c.event)
        level = level_and_title(c.title)[0]
        existing = self.rows('SELECT * FROM questions WHERE challenge_key=? ORDER BY number', (c.key,))
        if len(existing) > len(c.questions):
            raise ArchiveError('Question count decreased; existing discussion was preserved. Review the source before syncing.')
        known_ids = {q['source_id'] for q in existing if not re.fullmatch(r'q[1-9]\d*',q['source_id'])}
        if c.question_ids and not known_ids <= set(c.question_ids):
            raise ArchiveError('Source question identities changed; existing discussions were preserved. Reconcile before syncing.')
        with self.db:
            self.db.execute('''INSERT INTO challenges(key,event,season,competition,category,level,title,prompt,source,fingerprint,updated)
                VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET event=excluded.event,season=excluded.season,
                competition=excluded.competition,category=excluded.category,level=excluded.level,title=excluded.title,
                prompt=excluded.prompt,source=excluded.source,fingerprint=excluded.fingerprint,updated=excluded.updated''',
                (c.key,c.event,season,competition,c.category,level,c.title,c.prompt,c.url,fingerprint(c),now()))
            for number, text in enumerate(c.questions, 1):
                sid = c.question_ids[number-1] if c.question_ids else f'q{number}'
                # Older GitHub imports have positional IDs; retain those row keys and their links.
                old = next((q for q in existing if q['source_id'] == sid), None)
                if old is None:
                    old = next((q for q in existing if q['number'] == number and q['source_id'] == f'q{number}'), None)
                key = old['key'] if old else f'{c.key}/{sid}'
                match = re.search(r'\bQ\d+\s*[-–:]\s*(\d+)\s*points?', text, re.I)
                self.db.execute('''INSERT INTO questions(key,challenge_key,source_id,number,text,points) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET source_id=excluded.source_id,number=excluded.number,
                    text=excluded.text,points=excluded.points''', (key,c.key,sid,number,text,int(match[1]) if match else None))
        return self.rows('SELECT * FROM questions WHERE challenge_key=? ORDER BY number', (c.key,))

    def synced(self, key):
        with self.db:
            self.db.execute('UPDATE challenges SET synced_fingerprint=fingerprint WHERE key=?', (key,))

    def question(self, key=None, thread_id=None):
        field, value = ('q.key', key) if key is not None else ('q.thread_id', thread_id)
        return self.one(f'''SELECT q.*,c.title,c.prompt,c.event,c.season,c.competition,c.category,c.level,c.source
            FROM questions q JOIN challenges c ON c.key=q.challenge_key WHERE {field}=?''', (value,))

    def link_question(self, key, channel_id, message_id, thread_id):
        with self.db:
            self.db.execute('UPDATE questions SET channel_id=?,message_id=?,thread_id=? WHERE key=?',
                            (channel_id,message_id,thread_id,key))

    def search(self, keywords, filters, channels, *, include_legacy=False, offset=0, limit=5):
        tokens = re.findall(r'\w+', keywords, re.UNICODE)[:16]
        if not tokens:
            raise ArchiveError('Enter at least one searchable word.')
        match = ' AND '.join('"' + t + '"' for t in tokens)
        sql = '''SELECT q.*,c.title,c.event,c.category,c.level,c.season,c.competition,c.source
            FROM question_search f JOIN questions q ON q.key=f.question_key
            JOIN challenges c ON c.key=q.challenge_key WHERE question_search MATCH ?'''
        params = [match]
        clauses = []
        if channels:
            clauses.append('q.channel_id IN (' + ','.join('?' for _ in channels) + ')')
            params.extend(channels)
        if include_legacy:
            clauses.append('(q.channel_id IS NULL AND q.github_path IS NOT NULL)')
        if not clauses:
            return []
        sql += ' AND (' + ' OR '.join(clauses) + ')'
        for field in ('season','competition','category','level'):
            if filters.get(field):
                sql += f' AND c.{field}=? COLLATE NOCASE'
                params.append(filters[field])
        sql += ' ORDER BY rank,q.key LIMIT ? OFFSET ?'
        return self.rows(sql, (*params, limit, offset))

    def attachment(self, key, **values):
        if values:
            allowed = {'challenge_key','name','source','status','path','size','sha256','etag','modified',
                       'message_id','channel_id','error','updated'}
            if not values.keys() <= allowed:
                raise ValueError('Invalid attachment fields')
            values['updated'] = now()
            previous = self.one('SELECT * FROM attachments WHERE key=?', (key,))
            data = {**(previous or {}), **values, 'key': key}
            columns = list(data)
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO attachments (' + ','.join(columns) + ') VALUES (' +
                                ','.join('?' for _ in columns) + ')', [data[k] for k in columns])
        return self.one('SELECT * FROM attachments WHERE key=?', (key,))

    def verification(self, question_key, answer, user_id, result):
        with self.db:
            cur = self.db.execute('INSERT INTO verifications(question_key,answer,user_id,created,method,outcome,evidence) VALUES(?,?,?,?,?,?,?)',
                                  (question_key,answer,user_id,now(),result['method'],result['outcome'],result['evidence']))
        return cur.lastrowid

    def latest_verification(self, question_key):
        return self.one('SELECT * FROM verifications WHERE question_key=? ORDER BY id DESC LIMIT 1', (question_key,))

    def finish_verification(self, ident, result):
        with self.db:
            self.db.execute('UPDATE verifications SET method=?,outcome=?,evidence=? WHERE id=?',
                            (result['method'],result['outcome'],result['evidence'],ident))

    def interrupted_scans(self):
        rows = self.rows("SELECT * FROM scans WHERE finished IS NULL")
        with self.db:
            self.db.execute("UPDATE scans SET state='interrupted',finished=? WHERE finished IS NULL", (now(),))
        return rows

    async def import_manifest(self, raw, read_file):
        """Index version-2 GitHub archives without creating Discord content or sync markers."""
        entries = parse_manifest(raw)
        count = 0
        for key, entry in entries.items():
            texts, prompt = [], ''
            for item in entry['files']:
                raw_question = await read_file(item['path'])
                found = re.search(r'(?ms)^## Prompt\n\n(.*?)\n\n## Question \d+\n\n(.*?)(?:\n## Referenced files|\n---\n)', raw_question)
                if not found:
                    raise ArchiveError('An older question has an unfamiliar layout; reindex stopped without reposting.')
                prompt = found[1].rstrip()
                texts.append(found[2].rstrip())
            # Never replace richer current-source text or live question identities with redacted GitHub text.
            if not self.one('SELECT key FROM challenges WHERE key=?', (key,)):
                self.upsert_challenge(Challenge(entry['source'],entry['event'],entry['category'],entry['title'],prompt,tuple(texts)))
            with self.db:
                for item in entry['files']:
                    self.db.execute('UPDATE questions SET github_path=? WHERE challenge_key=? AND number=?',
                                    (item['path'],key,item['number']))
            count += len(texts)
        return count

    def close(self):
        self.db.close()
