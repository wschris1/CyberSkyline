"""One throttled progress message; discovery never pretends a total is known."""

import asyncio
from dataclasses import asdict, dataclass, field
import time

from .core import clean


@dataclass
class Progress:
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
    detail: str = ''
    started: float = field(default_factory=time.monotonic)
    scan_started: float | None = None

    def update(self, **values):
        for key, value in values.items():
            if key in self.__dataclass_fields__:
                setattr(self,key,value)

    def render(self, preview=False):
        elapsed = max(0, round(time.monotonic() - self.started))
        total = str(self.total) if self.total is not None else 'unknown (discovering)'
        eta = 'not available'
        if self.total and self.processed >= 3 and self.scan_started and self.processed < self.total:
            seconds = time.monotonic() - self.scan_started
            if seconds >= 10:
                eta = f'about {round(seconds / self.processed * (self.total-self.processed))}s (scan phase only)'
        text = (f'**NCL TRACKER — {self.state}**\n'
                f'**Mode:** {"Preview (no archive writes)" if preview else "Scan and archive"}\n'
                f'**Competition:** {clean(self.competition)[:180] or "Discovering"}\n'
                f'**Category:** {clean(self.category)[:100] or "—"}\n'
                f'**Challenge:** {clean(self.challenge)[:180] or "—"}\n'
                f'**Processed:** {self.processed} / {total}\n'
                f'**New:** {self.new} · **Skipped:** {self.skipped} · **Failed:** {self.failed}\n'
                f'**Files checked:** {self.attachments}/{self.attachment_total} · **File failures:** {self.attachment_failed}\n'
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
                # Status remains available via /skyline status; no duplicate replacement messages.
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
