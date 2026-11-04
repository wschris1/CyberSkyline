"""Bounded streaming downloads; credentials stay on their original HTTPS origin."""

import asyncio
from datetime import datetime, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import socket
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
    def __init__(self, store, max_bytes=64*1024*1024):
        self.store, self.max_bytes = store, max_bytes
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

    async def fetch(self, challenge, ref, context):
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
        jar = aiohttp.CookieJar()
        cookies = await context.cookies([ref.url])
        # Scope host cookies to Skyline. Never carry auth headers into redirects/CDNs.
        jar.update_cookies({c['name']:c['value'] for c in cookies}, response_url=URL('https://cyberskyline.com'))
        try:
            async with aiohttp.ClientSession(cookie_jar=jar,connector=aiohttp.TCPConnector(resolver=PublicResolver()),
                                            timeout=aiohttp.ClientTimeout(total=120),trust_env=False) as session:
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
                        if size_hint and size_hint > self.max_bytes:
                            return self.store.attachment(key,**base,status='oversized',size=size_hint,error='Exceeds local download limit.')
                        sha, size = hashlib.sha256(), 0
                        fd = os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
                        with os.fdopen(fd,'wb') as output:
                            async for chunk in response.content.iter_chunked(65536):
                                size += len(chunk)
                                if size > self.max_bytes:
                                    return self.store.attachment(key,**base,status='oversized',size=size,error='Exceeds local download limit.')
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
