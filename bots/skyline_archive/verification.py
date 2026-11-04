"""Evidence-based verification in a bounded child process; never platform submission."""

import asyncio
import json
import os
from pathlib import Path
import sys


OUTCOMES = {'Verified correct','Verified incorrect','Inconclusive','Verification error'}


def result(outcome, method, evidence):
    return dict(outcome=outcome,method=method,evidence=evidence)


def select_answer(messages, user_id, since=None):
    """Do not guess which discussion message is an answer. Preserve exact content."""
    candidates = [m for m in messages if m.author.id == user_id and not m.author.bot and m.content
                  and not m.content.startswith('/skyline ') and (since is None or m.created_at > since)]
    return candidates[0].content if len(candidates) == 1 else None, candidates


class Verifier:
    def __init__(self, store, attachments, timeout=15):
        self.store,self.attachments,self.timeout = store,attachments,timeout
        self.lock = asyncio.Lock()

    async def check(self, question, answer):
        if len(answer) > 4000:
            return result('Inconclusive','answer selection','Provide an answer of at most 4000 characters.')
        if self.lock.locked():
            return result('Verification error','worker','Another verification is running. Retry when it finishes.')
        files = []
        for row in self.store.rows('SELECT * FROM attachments WHERE challenge_key=?',(question['challenge_key'],)):
            path = self.attachments.local_path(row)
            if path and row['status'] in ('ready','uploaded','oversized-upload','upload-failed'):
                files.append(dict(name=row['name'],path=str(path),sha256=row['sha256']))
        payload = dict(question=question['text'],instructions=question['prompt'],answer=answer,files=files,
                       root=str(self.attachments.root.resolve()))
        async with self.lock:
            worker = Path(__file__).with_name('verify_worker.py')
            # Fixed executable and script. Challenge text and answers go only through stdin JSON.
            environment = {k:v for k,v in os.environ.items() if k in ('SYSTEMROOT','WINDIR','TEMP','TMP','LANG')}
            try:
                process = await asyncio.create_subprocess_exec(sys.executable,'-I',str(worker),stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=environment,
                    limit=65536,start_new_session=(os.name!='nt'))
            except OSError:
                return result('Verification error','worker','The configured verification runtime could not start.')
            try:
                output, _ = await asyncio.wait_for(process.communicate(json.dumps(payload).encode()),self.timeout)
                if process.returncode or len(output) > 16000:
                    return result('Verification error','worker','Verification tool failed or exceeded a resource limit.')
                data = json.loads(output)
                if data.get('outcome') not in OUTCOMES or not all(isinstance(data.get(k),str) for k in ('method','evidence')):
                    raise ValueError()
                return data
            except asyncio.TimeoutError:
                return result('Verification error','worker','Verification exceeded its time limit.')
            except (ValueError,UnicodeError):
                return result('Verification error','worker','Verification tool returned an invalid result.')
            finally:
                if process.returncode is None:
                    process.kill()
                await process.wait()
