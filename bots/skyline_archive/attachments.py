"""Bounded streaming downloads; credentials stay on their original HTTPS origin."""

import asyncio
from datetime import datetime, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import socket
import shutil
from urllib.parse import urljoin, urlsplit

from .core import ArchiveError, SessionExpired
from .storage import digest, now


def filename(value):
    # Strip path components in either platform's syntax, controls, and special device names.
    value = value.replace('\\','/').split('/')[-1]
    value = re.sub(r'[^\w .()\[\]-]', '_', value, flags=re.UNICODE).strip(' .')[:120] or 'attachment.bin'
    if re.match(r'(?i)^(con|prn|aux|nul|com\d|lpt\d)(\.|$)', value):
        value = '_' + value
    return value


def public_url(value):
    p = urlsplit(value)
    if (p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None,443)
            or len(value) > 8000 or any(c.isspace() for c in value)):
        raise ArchiveError('Attachment URL is not a supported public HTTPS URL.')
    if p.hostname == 'localhost' or p.hostname.endswith(('.local','.internal','.localhost')):
        raise ArchiveError('Attachment destination is not public.')
    try:
        address = ipaddress.ip_address(p.hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ArchiveError('Attachment destination is not public.')
    return p


class PublicResolver:
    async def resolve(self, host, port=0, family=socket.AF_INET):
        addresses = await asyncio.get_running_loop().getaddrinfo(host,port,type=socket.SOCK_STREAM,family=family)
        result = []
        for af, _, proto, _, address in addresses:
            if not ipaddress.ip_address(address[0]).is_global:
                raise ArchiveError('Attachment destination resolved to a non-public address.')
            result.append(dict(hostname=host,host=address[0],port=port,family=af,proto=proto,flags=socket.AI_NUMERICHOST))
        return result

    async def close(self):
        pass


class Attachments:
    def __init__(self, store, max_bytes=512*1024*1024, preferences=None):
        self.store, self.max_bytes = store, max_bytes
        self.preferences = preferences
        self.lock = asyncio.Lock()
        self.root = store.directory / 'artifacts'
        self.root.mkdir(exist_ok=True,mode=0o700)
        self.temp = self.root / 'temporary'
        self.temp.mkdir(exist_ok=True,mode=0o700)
        for path in self.temp.glob('*.part'):
            if path.is_file() and not path.is_symlink():
                path.unlink()

    def local_path(self, row):
        if not row or not row.get('path'):
            return None
        p = Path(row['path'])
        if p.is_symlink() or not p.resolve().is_relative_to(self.root.resolve()) or not p.is_file():
            return None
        return p

    def limits(self):
        prefs = self.preferences.effective() if self.preferences else {}
        return prefs.get('max_file_mb',self.max_bytes/1048576)*1048576,prefs.get('cache_mb',2048)*1048576

    def usage(self):
        return sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file() and not p.is_symlink())

    async def fetch(self, challenge, ref, context):
        async with self.lock:
            return await self._fetch(challenge,ref,context)

    def defer(self, challenge, ref):
        """Record work before publishing text, without touching the network or old files."""
        key = digest([challenge.key, urlsplit(ref.url).path])
        old = self.store.attachment(key)
        values = dict(challenge_key=challenge.key,name=filename(ref.name),source=ref.url)
        if old:
            return self.store.attachment(key,**values)
        return self.store.attachment(key,**values,status='pending',error=None)

    async def _fetch(self, challenge, ref, context):
        import aiohttp
        from yarl import URL
        key = digest([challenge.key, urlsplit(ref.url).path])
        old = self.store.attachment(key)
        name = filename(ref.name)
        base = dict(challenge_key=challenge.key,name=name,source=ref.url)
        p = public_url(ref.url)
        if p.hostname != 'cyberskyline.com' or not p.path.startswith('/artifact/'):
            return self.store.attachment(key,**base,status='unavailable',error='Not a recognized Cyber Skyline artifact link.')
        existing = self.local_path(old)
        headers = {}
        if existing:
            if old.get('etag'):
                headers['If-None-Match'] = old['etag']
            elif old.get('modified'):
                headers['If-Modified-Since'] = old['modified']
            elif (datetime.now(timezone.utc)-datetime.fromisoformat(
                    self.store.get('attachment-checked/'+key,old['updated']))).total_seconds() < 86400:
                if old['status'] not in ('ready','uploaded'):
                    return self.store.attachment(key,**base,status='ready',error=None)
                return old
        temporary = self.temp / (key + '.part')
        max_bytes,budget = self.limits()
        available = min(budget-await asyncio.to_thread(self.usage),shutil.disk_usage(self.root).free-128*1048576)
        jar = aiohttp.CookieJar()
        cookies = await context.cookies([ref.url])
        # Scope host cookies to Skyline. Never carry auth headers into redirects/CDNs.
        jar.update_cookies({c['name']:c['value'] for c in cookies}, response_url=URL('https://cyberskyline.com'))
        try:
            async with aiohttp.ClientSession(cookie_jar=jar,connector=aiohttp.TCPConnector(resolver=PublicResolver()),
                                            timeout=aiohttp.ClientTimeout(total=600,sock_read=45),trust_env=False) as session:
                target = ref.url
                for redirects in range(6):
                    dest = public_url(target)
                    if any(word in dest.path.lower() for word in ('/login','/signin','/sign-in')) and dest.hostname == 'cyberskyline.com':
                        raise SessionExpired('Cyber Skyline login expired while downloading a file. Refresh it and recheck the session.')
                    async with session.get(target,headers=headers,allow_redirects=False) as response:
                        if response.status in (301,302,303,307,308):
                            target = urljoin(target,response.headers.get('Location',''))
                            continue
                        if response.status == 401 and dest.hostname == 'cyberskyline.com':
                            raise SessionExpired('Cyber Skyline login expired during a file download.')
                        if response.status == 304 and existing:
                            self.store.put('attachment-checked/'+key,now())
                            return self.store.attachment(key,**base,status='ready',error=None)
                        if response.status >= 400:
                            return self.store.attachment(key,**base,status='unavailable',error=f'HTTP {response.status}')
                        size_hint = response.content_length
                        if size_hint and size_hint > max_bytes:
                            return self.store.attachment(key,**base,status='oversized',size=size_hint,error='Exceeds local download limit.')
                        if available <= 0 or (size_hint and size_hint > available):
                            return self.store.attachment(key,**base,status='cache-full',size=size_hint,error='Private cache budget or free disk space is insufficient; existing files were preserved.')
                        sha, size = hashlib.sha256(), 0
                        fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                        with os.fdopen(fd,'wb') as output:
                            async for chunk in response.content.iter_chunked(65536):
                                size += len(chunk)
                                if size > max_bytes:
                                    return self.store.attachment(key,**base,status='oversized',size=size,error='Exceeds local download limit.')
                                if size > available:
                                    return self.store.attachment(key,**base,status='cache-full',size=size,error='Private cache budget reached; existing files were preserved.')
                                output.write(chunk)
                                sha.update(chunk)
                        checksum = sha.hexdigest()
                        folder = self.root / key
                        folder.mkdir(exist_ok=True,mode=0o700)
                        destination = folder / (checksum[:16] + '-' + name)
                        os.replace(temporary,destination)
                        self.store.put('attachment-checked/'+key,now())
                        return self.store.attachment(key,**base,status='ready',path=str(destination),size=size,sha256=checksum,
                                                     etag=response.headers.get('ETag'),modified=response.headers.get('Last-Modified'),error=None)
                raise ArchiveError('Too many attachment redirects.')
        except SessionExpired:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ArchiveError, ValueError):
            return self.store.attachment(key,**base,status='failed',error='Download failed; retry the scan or open the source challenge.')
        finally:
            temporary.unlink(missing_ok=True)

    async def evidence(self, question, attachment, user_id, thread_id, message_id=None):
        """Copy an explicitly chosen Discord upload; never send source cookies to its CDN."""
        import aiohttp
        key = digest(['discord-evidence',question['key'],attachment.id])
        async with self.lock:
            old = self.store.attachment(key)
            if self.local_path(old) and old['status'] == 'ready':
                return old
            name = filename(attachment.filename)
            base = dict(challenge_key=question['challenge_key'],name=name,source='',status='pending')
            self.store.attachment(key,**base)
            with self.store.db:
                self.store.db.execute('INSERT OR REPLACE INTO evidence VALUES(?,?,?,?,?,?)',
                    (key,question['key'],user_id,thread_id,message_id,now()))
            temporary = self.temp/(key+'.part')
            try:
                host = public_url(attachment.url).hostname
                if host not in ('cdn.discordapp.com','media.discordapp.net'):
                    raise ArchiveError('Only Discord-uploaded attachments are accepted as supplemental evidence.')
                maximum,budget = self.limits()
                available = min(budget-await asyncio.to_thread(self.usage),shutil.disk_usage(self.root).free-128*1048576)
                if attachment.size > maximum or attachment.size > available:
                    raise ArchiveError('Evidence exceeds the file/cache limit or available disk space. Adjust /ws settings if appropriate.')
                async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(resolver=PublicResolver()),
                    timeout=aiohttp.ClientTimeout(total=600,sock_read=45),trust_env=False) as session:
                    async with session.get(attachment.url,allow_redirects=False) as response:
                        if response.status != 200:
                            raise ArchiveError('Discord evidence could not be downloaded. Reattach the file and retry.')
                        sha,size = hashlib.sha256(),0
                        fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                        with os.fdopen(fd,'wb') as output:
                            async for chunk in response.content.iter_chunked(65536):
                                size += len(chunk)
                                if size > min(maximum,available):
                                    raise ArchiveError('Evidence reached the private storage limit.')
                                output.write(chunk); sha.update(chunk)
                folder = self.root/key
                folder.mkdir(exist_ok=True,mode=0o700)
                destination = folder/(sha.hexdigest()[:16]+'-'+name)
                os.replace(temporary,destination)
                return self.store.attachment(key,status='ready',path=str(destination),size=size,sha256=sha.hexdigest(),error=None)
            except (aiohttp.ClientError,asyncio.TimeoutError,OSError,ArchiveError,ValueError) as exc:
                error = str(exc) if isinstance(exc,ArchiveError) else 'Evidence download failed; reattach and retry.'
                return self.store.attachment(key,status='failed',error=error)
            finally:
                temporary.unlink(missing_ok=True)
