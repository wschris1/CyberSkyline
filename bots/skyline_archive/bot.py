"""Owner-only Discord slash commands; no message-content intent required."""

import asyncio
import logging
import time

import aiohttp
import discord
from discord import app_commands

from .core import ArchiveError, skyline_url
from .github import GitHub
from .scanner import Scanner
from .survey import SurveyManager, SurveyProbe


LOG = logging.getLogger(__name__)


class SkylineCommands(app_commands.Group):
    def __init__(self, client):
        super().__init__(name="skyline", description="Archive challenge questions and watch for surveys.", guild_only=True)
        self.client = client

    async def interaction_check(self, interaction):
        if (interaction.guild_id != self.client.settings.guild_id
                or interaction.user.id not in self.client.settings.owners):
            await interaction.response.send_message("This bot is restricted to its configured owners and server.", ephemeral=True)
            return False
        return True

    async def on_error(self, interaction, error):
        original = getattr(error, "original", error)
        message = str(original) if isinstance(original, ArchiveError) else "Command failed. Check the bot host and configuration."
        if interaction.response.is_done():
            await interaction.followup.send(message[:1900], ephemeral=True)
        else:
            await interaction.response.send_message(message[:1900], ephemeral=True)

    @app_commands.command(name="sync", description="Scan one Cyber Skyline event and upload its questions.")
    @app_commands.describe(event_url="The event overview URL (/world/...).", preview="Count and validate only; do not upload.")
    async def sync(self, interaction: discord.Interaction, event_url: str | None = None, preview: bool = False):
        target = skyline_url(event_url or self.client.settings.event_url)
        self.client.start_sync(target, preview=preview)
        await interaction.response.send_message("Scan started. Use `/skyline status` for progress and the final GitHub link.", ephemeral=True)

    @app_commands.command(name="sync-all", description="Scan every event still accessible on your Competition dashboard.")
    async def sync_all(self, interaction: discord.Interaction, preview: bool = False):
        self.client.start_sync(all_events=True, preview=preview)
        await interaction.response.send_message("Scanning accessible events. Closed events will be listed as skipped. Use `/skyline status` for results.", ephemeral=True)

    @app_commands.command(name="status", description="Show scan progress, result, and automatic-sync settings.")
    async def status(self, interaction: discord.Interaction):
        interval = self.client.settings.interval
        schedule = f"Every {interval} minutes" if interval else "Off"
        await interaction.response.send_message(
            (f"**Archive:** {self.client.archive_status}\n**Automatic sync:** {schedule}\n"
             f"**Repository:** https://github.com/{self.client.settings.repository}")[:1950], ephemeral=True)

    @app_commands.command(name="watch-survey", description="Ping you here when a survey website actually loads a usable form.")
    @app_commands.describe(challenge_url="The Survey challenge URL (/module/.../.../...).",
                           survey_url="Optional actual survey link, useful while the challenge link is blank.",
                           ready_text="Optional text that must appear on the usable form, such as its title.")
    async def watch_survey(self, interaction: discord.Interaction, challenge_url: str,
                           survey_url: str = "", ready_text: str = ""):
        if interaction.channel_id is None:
            raise ArchiveError("Run this command in the channel where you want the ping.")
        key = self.client.surveys.add(challenge_url, survey_url, ready_text, interaction.user.id,
                                      interaction.channel_id, interaction.guild_id)
        await interaction.response.send_message(
            f"Watch `{key}` saved. I will check about once a minute while the bot is running and ping you here after the form is ready on two checks. "
            "Use `/skyline survey-status` to see what is loading.", ephemeral=True)

    @app_commands.command(name="survey-status", description="Show your saved survey watches and last readiness checks.")
    async def survey_status(self, interaction: discord.Interaction):
        rows = [f"`{key}` — **{item['delivery']}**: {item['status']}"
                for key, item in self.client.surveys.watches.items() if item["owner_id"] == interaction.user.id]
        await interaction.response.send_message("\n".join(rows)[:1950] or "You have no saved survey watches.", ephemeral=True)

    @app_commands.command(name="unwatch-survey", description="Remove one of your survey watches, including a finished watch.")
    async def unwatch_survey(self, interaction: discord.Interaction, watch_id: str):
        watch = self.client.surveys.watches.get(watch_id)
        if not watch or watch["owner_id"] != interaction.user.id:
            raise ArchiveError("That watch was not found for your account.")
        del self.client.surveys.watches[watch_id]
        self.client.surveys.save()
        await interaction.response.send_message(f"Removed watch `{watch_id}`.", ephemeral=True)


class SkylineBot(discord.Client):
    def __init__(self, settings):
        super().__init__(intents=discord.Intents(guilds=True), allowed_mentions=discord.AllowedMentions.none())
        self.settings = settings
        self.tree = app_commands.CommandTree(self)
        self.tree.add_command(SkylineCommands(self), guild=discord.Object(id=settings.guild_id))
        self.archive_status = "No scan run yet."
        self.scan_task = None
        self.background = []
        self.http_session = None
        self.surveys = SurveyManager(settings.state_dir / "survey-watches.json", SurveyProbe(settings), self.send_survey_ping)

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession()
        await self.tree.sync(guild=discord.Object(id=self.settings.guild_id))
        self.background.append(asyncio.create_task(self.survey_loop()))
        if self.settings.interval:
            self.background.append(asyncio.create_task(self.schedule_loop()))

    def start_sync(self, event_url=None, all_events=False, preview=False):
        if self.scan_task and not self.scan_task.done():
            raise ArchiveError("A scan is already running. Use /skyline status to check it.")
        self.archive_status = "Starting scan…"
        self.scan_task = asyncio.create_task(self.run_sync(event_url, all_events, preview))

    async def run_sync(self, event_url, all_events, preview):
        started = time.monotonic()
        try:
            scanner = Scanner(self.settings, lambda text: setattr(self, "archive_status", text))
            result = await scanner.collect(event_url, all_events)
            count = len(result.challenges)
            question_count = sum(len(c.questions) for c in result.challenges)
            skipped = len(result.skipped_events)
            if result.errors:
                detail = " ".join(result.errors[:3])
                raise ArchiveError(f"Collected {count} challenges but {len(result.errors)} page(s) failed. Nothing uploaded. {detail}")
            if not count:
                raise ArchiveError(f"No accessible questions found. {skipped} unavailable event(s) skipped. Nothing uploaded.")
            summary = f"{count} challenges / {question_count} questions; {skipped} event(s) skipped."
            if preview:
                self.archive_status = "Preview complete: " + summary + " Nothing uploaded."
            else:
                self.archive_status = "Publishing " + summary
                publication = await GitHub(self.settings, self.http_session).publish(result.challenges)
                self.archive_status = "Complete: " + summary
                self.archive_status += f" {publication.changed} files changed. {publication.commit_url}" if publication.changed else " GitHub is already up to date."
            self.archive_status += f" Took {round(time.monotonic() - started)} seconds."
            if result.skipped_events:
                self.archive_status += " Skipped: " + ", ".join(result.skipped_events)
        except ArchiveError as exc:
            self.archive_status = str(exc)
        except Exception as exc:
            # Do not echo page contents, tokens, auth paths, or raw HTTP bodies to Discord/logs.
            self.archive_status = f"Scan failed ({type(exc).__name__}). Check the host, browser installation, and saved login."
            LOG.error("Archive scan failed (%s)", type(exc).__name__)

    async def send_survey_ping(self, watch, url):
        if watch["owner_id"] not in self.settings.owners or watch["guild_id"] != self.settings.guild_id:
            raise ArchiveError("Survey watch owner/server is no longer allowed.")
        channel = self.get_channel(watch["channel_id"]) or await self.fetch_channel(watch["channel_id"])
        if not getattr(channel, "guild", None) or channel.guild.id != self.settings.guild_id:
            raise ArchiveError("The survey channel is outside the configured server.")
        # Mention exactly the user who requested this watch, never a role or everyone.
        message = await channel.send(
            f"<@{watch['owner_id']}> The survey form is ready to fill out.\n<{url}>\n"
            f"Challenge: <{watch['challenge_url']}>",
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False,
                                                     users=[discord.Object(id=watch["owner_id"])], replied_user=False))
        return message.id

    async def survey_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self.surveys.tick()
            except Exception as exc:
                LOG.error("Survey state could not be updated (%s)", type(exc).__name__)
            await asyncio.sleep(60)

    async def schedule_loop(self):
        await self.wait_until_ready()
        while not self.is_closed():
            if not self.scan_task or self.scan_task.done():
                self.start_sync(self.settings.event_url)
            await asyncio.sleep(self.settings.interval * 60)

    async def close(self):
        tasks = self.background + ([self.scan_task] if self.scan_task else [])
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if self.http_session:
            await self.http_session.close()
        await super().close()
