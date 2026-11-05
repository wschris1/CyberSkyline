"""Persisted owner settings override environment defaults; secrets are never editable here."""

from .core import ArchiveError


DEFAULTS = dict(enabled=False,frequency=60,archive_enabled=False,archive_hub=0,notification_channel=0,
                notify_login=True,notify_results=False,default_preview=False,category_prefix='',ai_enabled=False)


class Preferences:
    def __init__(self, store, settings):
        self.store, self.settings = store, settings

    def effective(self):
        defaults = {**DEFAULTS,
                    'enabled': bool(self.settings.interval), 'frequency': self.settings.interval or 60,
                    'archive_hub': getattr(self.settings,'archive_hub',0),
                    'archive_enabled': bool(getattr(self.settings,'archive_hub',0)),
                    'notification_channel':getattr(self.settings,'notification_channel',0),
                    'default_preview':getattr(self.settings,'default_preview',False),
                    'ai_enabled':getattr(self.settings,'ai_verify_enabled',False)}
        return {k:self.store.get(k,v,'settings') for k,v in defaults.items()}

    async def save(self, values, guild):
        if not values.keys() <= DEFAULTS.keys():
            raise ArchiveError('Unknown setting.')
        result = {**self.effective(),**values}
        for key in ('enabled','archive_enabled','notify_login','notify_results','default_preview','ai_enabled'):
            if type(result[key]) is not bool:
                raise ArchiveError(f'{key} must be true or false.')
        if values.get('ai_enabled') and not getattr(self.settings,'openai_api_key',''):
            raise ArchiveError('Set OPENAI_API_KEY in the private PebbleHost configuration and restart before enabling AI. Never paste keys into Discord.')
        if type(result['frequency']) is not int or not 10 <= result['frequency'] <= 10080:
            raise ArchiveError('Automatic scan frequency must be 10–10080 minutes.')
        if not isinstance(result['category_prefix'],str) or len(result['category_prefix']) > 35:
            raise ArchiveError('Category prefix must be at most 35 characters.')
        for key in ('archive_hub','notification_channel'):
            ident = result[key]
            if type(ident) is not int or ident < 0:
                raise ArchiveError('Choose a valid destination channel.')
            if ident:
                channel = guild.get_channel(ident) or await guild.fetch_channel(ident)
                if channel.guild.id != self.settings.guild_id or not hasattr(channel,'send') or getattr(channel,'parent_id',None):
                    raise ArchiveError('Select a text channel in the configured server.')
                permissions = channel.permissions_for(guild.me)
                needed = ('view_channel','send_messages','read_message_history','embed_links')
                if not all(getattr(permissions,p,False) for p in needed):
                    raise ArchiveError('The bot needs View Channel, Send Messages, Read Message History and Embed Links there.')
        if result['archive_enabled']:
            if not result['archive_hub']:
                raise ArchiveError('Select an archive hub channel before enabling the Discord archive.')
            needed = ('manage_channels','create_public_threads','send_messages_in_threads','attach_files','manage_threads')
            if not all(getattr(guild.me.guild_permissions,p,False) for p in needed):
                raise ArchiveError('Grant the bot Manage Channels, Manage Threads, Create Public Threads, Send Messages in Threads and Attach Files.')
        if result['enabled'] and not (result['archive_hub'] or result['notification_channel']):
            raise ArchiveError('Scheduled scans need an archive hub or notification channel for progress.')
        self.store.save_settings(values)
        return self.effective()

    async def mapping(self, guild, category, level, channel):
        import discord
        if not category.strip() or len(category) > 100:
            raise ArchiveError('Provide the source category name, at most 100 characters.')
        if channel.guild.id != self.settings.guild_id:
            raise ArchiveError('The mapping must stay in the configured server.')
        if level and level not in ('easy','medium','hard','unrated'):
            raise ArchiveError('Difficulty must be easy, medium, hard or unrated.')
        if level:
            if not isinstance(channel,discord.TextChannel):
                raise ArchiveError('Choose a text channel for a difficulty mapping.')
            needed = ('view_channel','send_messages','read_message_history','embed_links','attach_files',
                      'create_public_threads','send_messages_in_threads','manage_threads')
            scope,kind = category.casefold()+'/'+level,'channel'
        else:
            if not isinstance(channel,discord.CategoryChannel):
                raise ArchiveError('Choose a Discord category for a category mapping.')
            needed = ('view_channel','manage_channels')
            scope,kind = category.casefold(),'category'
        if not all(getattr(channel.permissions_for(guild.me),p,False) for p in needed):
            raise ArchiveError('The bot lacks permissions required for that mapping.')
        self.store.map(kind,scope,channel.id)
        # Existing questions retain their own channel/message/thread IDs.
