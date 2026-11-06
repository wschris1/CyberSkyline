"""One throttled progress message; discovery never pretends a total is known."""

import asyncio
from dataclasses import asdict, dataclass, field
import time

from .core import clean


@dataclass
class Progress:
    workflow: str = 'both'
    collecting: bool = False
    discord_completed: int = 0
    discord_challenge: str = ''
    publication_failed: int = 0
    state: str = 'discovering challenges'
    competition: str = ''
    category: str = ''
    challenge: str = ''
    processed: int = 0
    total: int | None = None
    new: int = 0
    skipped: int = 0
    failed: int = 0
    attachments: int = 0
    attachment_total: int = 0
    attachment_failed: int = 0
    uploaded: int = 0
    upload_failed: int = 0
    detail: str = ''
    started: float = field(default_factory=time.monotonic)
    scan_started: float | None = None
    scan_offset: int = 0
    finished: float | None = None
    elapsed_before: float = 0

    def update(self, **values):
        for key, value in values.items():
            if key in self.__dataclass_fields__:
                setattr(self,key,value)
        if values.get('state') in ('completed','completed with errors','failed','stopped','paused','interrupted',
                                  'waiting for login','waiting for event','discovery complete') and self.finished is None:
            self.finished = time.monotonic()

    def render(self, preview=False):
        clock = self.finished if self.finished is not None else time.monotonic()
        elapsed = max(0, round(clock - self.started + self.elapsed_before))
        total = str(self.total) if self.total is not None else 'unknown (discovering)'
        eta = 'not available'
        samples = self.processed-self.scan_offset
        if self.finished is None and self.state == 'scanning' and self.total and samples >= 3 and self.scan_started and self.processed < self.total:
            seconds = time.monotonic() - self.scan_started
            if seconds >= 10:
                eta = f'about {round(seconds / samples * (self.total-self.processed))}s (scan phase only)'
        mode = {'discord':'Discord only','github':'Discord archive → GitHub','both':'Discord first, then GitHub'}[self.workflow]
        text = (f'**WS — {self.state}**\n'
                f'**Mode:** {"Preview (no archive writes) — " if preview else ""}{mode}\n'
                f'**Competition:** {clean(self.competition)[:180] or "Discovering"}\n'
                f'**Category:** {clean(self.category)[:100] or "—"}\n'
                f'**Challenge:** {clean(self.challenge)[:180] or "—"}\n'
                f'**Processed:** {self.processed} / {total}\n'
                f'**New:** {self.new} · **Skipped:** {self.skipped} · **Failed:** {self.failed+self.publication_failed}\n'
                f'**Discord archives completed:** {self.discord_completed} · **Posting:** {clean(self.discord_challenge)[:100] or "—"}\n'
                f'**Files downloaded/cached:** {self.attachments}/{self.attachment_total} · **Download failures:** {self.attachment_failed}\n'
                f'**Files uploaded/linked:** {self.uploaded} · **Upload failures/oversized:** {self.upload_failed}\n'
                f'**Elapsed:** {elapsed}s · **Remaining:** {eta}\n{self.detail}')
        return text[:1950]


class ProgressMessage:
    def __init__(self, message, progress, preview, interval=5, checkpoint=None):
        self.message, self.progress, self.preview = message, progress, preview
        self.interval = max(5, interval)
        self.last_text = None
        self.stopped = asyncio.Event()
        self.task = None
        self.checkpoint = checkpoint

    def start(self):
        self.task = asyncio.create_task(self.loop())

    async def edit(self):
        text = self.progress.render(self.preview)
        if self.checkpoint:
            self.checkpoint()
        if text != self.last_text:
            try:
                await self.message.edit(content=text)
            except Exception:
                # Status remains available via /ws status; no duplicate replacement messages.
                return
            self.last_text = text

    async def loop(self):
        while not self.stopped.is_set():
            try:
                await asyncio.wait_for(self.stopped.wait(), self.interval)
            except asyncio.TimeoutError:
                await self.edit()

    async def finish(self):
        self.stopped.set()
        if self.task:
            await self.task
        await self.edit()
