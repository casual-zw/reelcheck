"""Retrieve a reviewed source manifest, retaining explicit failures for review."""
from collect import ROOT, DATA, append, now
from fireworks_client import load
from evidence import add


if __name__ == '__main__':
    for key, urls in load(ROOT / 'evidence_sources.json').items():
        for url in urls:
            try:
                add(key, [url])
            except Exception as error:
                append(DATA / 'labeling' / 'evidence_errors.jsonl',
                       {'key': key, 'url': url, 'error': str(error), 'at': now()})
                print(f'Unavailable for {key}: {url}', flush=True)
