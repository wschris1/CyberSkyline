"""Preview first; one authorized owner must explicitly confirm irreversible cleanup."""

import asyncio
import time

import discord

from .cleanup import Cleanup, WARNING, locked
from .core import ArchiveError
from .ui import OwnerView, diagnostic_text


class CleanupView(OwnerView):
    def __init__(self,client,owner,plan):
        super().__init__(client,owner,timeout=600)
        self.plan,self.page,self.used,self.message = plan,0,False,None
        async def previous(i):
            self.page=max(0,self.page-1)
            await i.response.edit_message(content=self.render(),view=self)
        async def following(i):
            self.page+=1
            await i.response.edit_message(content=self.render(),view=self)
        async def confirm(i):
            if self.used or time.monotonic()-plan.created>600:
                raise ArchiveError('This preview is closed or expired. Run /skyline-cleanup preview again.')
            if client.busy():
                raise ArchiveError('Wait for the current scan or pause it, then run a fresh cleanup preview.')
            await i.response.send_modal(CleanupConfirmation(self))
        async def cancel(i):
            self.used=True
            self.stop()
            await i.response.edit_message(content='Cleanup cancelled. Nothing was deleted.',view=None)
        self.button('Previous',previous)
        self.button('Next',following)
        self.button('Delete listed archives…',confirm,disabled=not plan.items,style=discord.ButtonStyle.danger,row=2)
        self.button('Cancel',cancel,row=2)

    def render(self):
        plan=self.plan
        rows=[*plan.items,*[dict(i,kind='kept') for i in plan.skipped]]
        pages=max(1,(len(rows)+3)//4)
        self.page=min(self.page,pages-1)
        self.children[0].disabled=self.page==0
        self.children[1].disabled=self.page>=pages-1
        clean=lambda s,n=100:diagnostic_text(s,self.client.settings,n)
        lines=['**Discord cleanup — preview only**',
               f'**Eligible:** {len(plan.channels)} channels · {len(plan.categories)} empty-after-cleanup categories',
               f'**Kept:** {len(plan.skipped)} · **Page:** {self.page+1}/{pages}',
               f'[Verified GitHub commit](https://github.com/{plan.repository}/commit/{plan.head}) · branch `{clean(plan.branch)}`',
               '**Nothing has been deleted.** '+WARNING,
               'Scheduled scans will leave removed archives retired. Manual scans can rebuild prompts, but cannot restore deleted discussions.']
        for item in rows[self.page*4:self.page*4+4]:
            label='KEEP' if item['kind']=='kept' else 'DELETE '+item['kind'].upper()
            lines.append(f"**{label}:** {clean(item['name'],70)} (`{item['id']}`)"+
                         (' — '+clean(item['reason'],140) if item.get('reason') else ''))
        if not plan.items:
            lines.append('No eligible archives. Export missing/current questions to GitHub first, then preview again.')
        return '\n\n'.join(lines)[:1950]


class CleanupConfirmation(discord.ui.Modal):
    def __init__(self,view):
        super().__init__(title='Permanently delete Discord archives',timeout=180)
        self.view=view
        self.confirmation=discord.ui.TextInput(label='Type this exact phrase to confirm',
            placeholder=view.plan.phrase,max_length=100)
        self.add_item(self.confirmation)

    async def interaction_check(self,i):
        return await self.view.interaction_check(i)

    async def on_submit(self,i):
        view=self.view
        # Repeat the authorization at the irreversible entry point, not just on the button.
        if not await view.interaction_check(i):
            return
        if view.used or time.monotonic()-view.plan.created>600:
            await i.response.send_message('Preview expired or already used. Run /skyline-cleanup preview again.',ephemeral=True)
            return
        if str(self.confirmation)!=view.plan.phrase:
            await i.response.send_message('The confirmation phrase did not match. Nothing was deleted.',ephemeral=True)
            return
        view.used=True
        view.stop()
        await i.response.defer(ephemeral=True,thinking=True)
        last=0
        async def notify(done,total):
            nonlocal last
            if time.monotonic()-last>=5:
                last=time.monotonic()
                try:
                    await i.edit_original_response(content=f'Discord cleanup: {done}/{total} listed items removed. GitHub is unchanged.')
                except discord.HTTPException:
                    pass
        try:
            cleanup=Cleanup(view.client)
            removed,failures=await locked(view.client,'cleanup deleting',lambda:cleanup.execute(view.plan,i.user.id,notify))
            channels=sum(x['kind']=='channel' for x in removed)
            categories=len(removed)-channels
            text=f'**Discord cleanup complete:** {channels} channels and {categories} categories removed. GitHub was not changed.\n'
            text+='Removed archives are excluded from scheduled Discord posting. Private source data, files and verification records were retained.'
            if failures:
                text+='\n**Kept / needs review:**\n'+'\n'.join(diagnostic_text(x,view.client.settings,220) for x in failures[:5])
                text+='\nRun a new preview to reconcile or retry remaining items.'
        except asyncio.CancelledError:
            text='Cleanup stopped. Completed deletions cannot be undone. Pending results will be reconciled on restart or the next cleanup preview; no automatic deletes will be retried.'
        except (ArchiveError,discord.HTTPException) as exc:
            text=(str(exc) if isinstance(exc,ArchiveError) else 'Discord could not be checked. Cleanup stopped; run a fresh preview.')
            text+='\nAny already completed deletions cannot be undone. Review a fresh preview before retrying.'
        except Exception:
            text='Cleanup stopped after an unexpected error. Completed deletions cannot be undone; run a new preview to reconcile pending results.'
        await i.edit_original_response(content=text[:1950],view=None)
        if view.message:
            try:
                await view.message.edit(view=None)
            except discord.HTTPException:
                pass


async def preview(client,interaction,scope):
    await interaction.response.defer(ephemeral=True)
    cleanup=Cleanup(client)
    async def build():
        await cleanup.recover()
        origin=getattr(interaction.channel,'parent_id',None) or interaction.channel_id
        return await cleanup.plan(scope,origin)
    plan=await locked(client,'cleanup preview',build)
    view=CleanupView(client,interaction.user.id,plan)
    view.message=await interaction.followup.send(view.render(),view=view,ephemeral=True,wait=True)


async def allow_recreation(client,interaction,scope):
    await interaction.response.defer(ephemeral=True)
    async def update():
        return Cleanup(client).allow_recreation(scope)
    count=await locked(client,'cleanup settings',update)
    await interaction.followup.send(f'{count} retired challenge(s) may be recreated by future scans. This does not restore deleted Discord messages or discussions.',ephemeral=True)
