"""Fetch attributable public evidence; model-generated URLs are never evidence."""
import argparse
import hashlib
import ipaddress
import socket
from urllib.parse import urlparse, urljoin
import requests
from bs4 import BeautifulSoup
from collect import DATA, now
from fireworks_client import digest, load, save


def public_https(url):
    parsed = urlparse(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError('Evidence URLs must be public HTTPS URLs without credentials')
    addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Private or local network addresses cannot be fetched as evidence')


def fetch(url):
    original = url
    for _ in range(5):
        public_https(url)
        with requests.get(url, timeout=(15, 40), allow_redirects=False, stream=True,
                          headers={'User-Agent': 'VideoFactCheckResearch/0.1'}) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers['Location'])
                continue
            response.raise_for_status()
            mime = response.headers.get('Content-Type', '')
            if not any(x in mime for x in ['text/html', 'text/plain', 'application/xhtml']):
                raise ValueError('Unsupported evidence content type: ' + mime)
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 4_000_000:
                    raise ValueError('Evidence page exceeds 4 MB')
                chunks.append(chunk)
            raw = b''.join(chunks)
            page = BeautifulSoup(raw, 'html.parser')
            title = page.title.get_text(' ', strip=True) if page.title else url
            date_node = page.find('meta', property='article:published_time') or page.find('meta', attrs={'name': 'date'})
            published = date_node.get('content') if date_node else None
            links = [{'text': a.get_text(' ', strip=True), 'url': urljoin(url, a['href'])}
                     for a in page.find_all('a', href=True) if a.get_text(' ', strip=True)]
            for tag in page(['script', 'style', 'nav', 'footer', 'header', 'form', 'noscript']):
                tag.decompose()
            main = page.find('article') or page.find('main') or page.body or page
            text = main.get_text(' ', strip=True)
            if len(text) < 150:
                raise ValueError('Evidence page has insufficient readable text')
            record = {'url': original, 'resolved_url': url, 'title': title,
                'publisher': urlparse(url).hostname, 'published_at': published, 'retrieved_at': now(),
                'text': text[:250000], 'truncated': len(text) > 250000, 'links': links,
                'retrieval_method': 'direct_https', 'http_status': response.status_code,
                'body_sha256': hashlib.sha256(raw).hexdigest(), 'text_sha256': digest(text[:250000])}
            record['evidence_id'] = 'e_' + digest({'url': original, 'text': record['text']})[:16]
            return record
    raise ValueError('Too many evidence redirects')


def add(key, urls):
    root = DATA / 'labeling' / 'evidence'
    path = root / (key + '.json')
    records = load(path)['sources'] if path.exists() else []
    known = {r['url'] for r in records}
    for url in urls:
        if url in known:
            continue
        cache = root / 'pages' / (digest(url) + '.json')
        record = load(cache) if cache.exists() else fetch(url)
        save(cache, record)
        records.append(record)
        known.add(url)
        save(path, {'video_key': key, 'sources': records, 'updated_at': now()})
        print(f"{key}: added {record['evidence_id']} ({record['publisher']})", flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--key', required=True)
    p.add_argument('--url', action='append', required=True)
    args = p.parse_args()
    if not all(c.isalnum() or c in '_-' for c in args.key):
        raise ValueError('Invalid video key')
    add(args.key, args.url)


if __name__ == '__main__':
    main()
