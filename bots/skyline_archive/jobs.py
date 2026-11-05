"""Durable scan checkpoints. Completed items are never rescanned on resume."""

from dataclasses import asdict
import json

from .core import ArchiveError
from .storage import now


class Jobs:
    def __init__(self, store):
        self.store = store

    def create(self, options, preview):
        with self.store.db:
            cur = self.store.db.execute('INSERT INTO scans(state,preview,scope,progress,started) VALUES(?,?,?,?,?)',
                ('discovering',int(preview),json.dumps(options.get('scope',{})),'{}',now()))
            ident = cur.lastrowid
            self.store.db.execute('INSERT INTO scan_jobs(id,options) VALUES(?,?)',(ident,json.dumps(options)))
        return ident

    def get(self, ident):
        return self.store.one('SELECT s.*,j.options,j.discovery_complete FROM scans s JOIN scan_jobs j ON j.id=s.id WHERE s.id=?',(ident,))

    def latest(self, failed=False):
        where = "EXISTS(SELECT 1 FROM scan_items i WHERE i.scan_id=s.id AND i.state='failed') OR s.state IN ('failed','completed with errors')" if failed else "s.state IN ('paused','interrupted','stopped','waiting for login')"
        return self.store.one('SELECT s.*,j.options,j.discovery_complete FROM scans s JOIN scan_jobs j ON j.id=s.id WHERE '+where+' ORDER BY s.id DESC LIMIT 1')

    def catalog(self, ident, entries, complete=True):
        with self.store.db:
            for entry in entries:
                self.store.db.execute("INSERT INTO scan_items(scan_id,url,entry,state) VALUES(?,?,?,'pending') ON CONFLICT(scan_id,url) DO UPDATE SET entry=excluded.entry",
                    (ident,entry['url'],json.dumps(entry)))
            self.store.db.execute('UPDATE scan_jobs SET discovery_complete=? WHERE id=?',(int(complete),ident))

    def items(self, ident, *states):
        sql = 'SELECT * FROM scan_items WHERE scan_id=?'
        if states:
            sql += ' AND state IN ('+','.join('?' for _ in states)+')'
        return self.store.rows(sql+' ORDER BY rowid',(ident,*states))

    def capture(self, ident, c):
        with self.store.db:
            self.store.db.execute("UPDATE scan_items SET payload=?,state='collected',error=NULL WHERE scan_id=? AND url=?",
                (json.dumps(asdict(c)),ident,c.url))

    def state(self, ident, url, state, error=None):
        with self.store.db:
            self.store.db.execute('UPDATE scan_items SET state=?,error=? WHERE scan_id=? AND url=?',(state,error,ident,url))

    def prepare_resume(self, ident, retry=False):
        row = self.get(ident)
        if not row:
            raise ArchiveError('No resumable scan checkpoint exists.')
        with self.store.db:
            # Publication failures retain their complete payload; page failures do not.
            self.store.db.execute("UPDATE scan_items SET state=CASE WHEN payload IS NULL THEN 'pending' ELSE 'collected' END,error=NULL WHERE scan_id=? AND state='failed'",(ident,))
            self.store.db.execute("UPDATE scans SET state='resuming',finished=NULL WHERE id=?",(ident,))
        return row
