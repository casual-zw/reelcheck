#!/usr/bin/env python3
"""Find original-video leads on Full Fact; every link needs a role/claim review."""
import html
import json
import re
import time
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, parse_qs
import requests
from collect import DATA, append, now, write_jsonl


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in {"a", "iframe"}:
            self.links.append(attrs.get("href", attrs.get("src", "")))
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def fetch(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    parser = Links()
    parser.feed(response.text)
    return parser


def canonical_video(url):
    url = html.unescape(url)
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"youtube.com", "m.youtube.com", "youtu.be"}:
        vid = None
        parts = parsed.path.strip("/").split("/")
        if host == "youtu.be":
            vid = parts[0]
        elif parts[0] in {"shorts", "embed"} and len(parts) > 1:
            vid = parts[1]
        elif parsed.path == "/watch":
            vid = parse_qs(parsed.query).get("v", [None])[0]
        if vid and re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
            return "youtube", vid, f"https://www.youtube.com/watch?v={vid}"
    if host in {"tiktok.com", "m.tiktok.com"}:
        match = re.search(r"/(@[^/]+)/video/(\d+)", parsed.path)
        if match:
            return "tiktok", match[2], "https://www.tiktok.com" + match[0]
    if host == "instagram.com":
        match = re.search(r"/(?:reel|reels|p)/([\w-]+)", parsed.path)
        if match:
            return "instagram", match[1], "https://www.instagram.com" + match[0] + "/"
    return None


def main():
    article_urls = set()
    sections = {"health", "politics", "economy", "environment", "technology", "online",
                "news", "crime", "immigration", "culture-and-society", "conflict"}
    for page in range(1, 6):
        index = fetch(f"https://fullfact.org/tiktok/?page={page}")
        for link in index.links:
            url = urljoin("https://fullfact.org/", link)
            p = urlparse(url)
            parts = p.path.strip("/").split("/")
            if p.netloc == "fullfact.org" and len(parts) == 2 and parts[0] in sections:
                article_urls.add(url)
        time.sleep(1)
    rows = {}
    for i, article in enumerate(sorted(article_urls)):
        try:
            page = fetch(article)
            category = urlparse(article).path.split("/")[1]
            category_map = {"health": "health_medicine", "politics": "politics_society",
                "economy": "finance_economy", "environment": "climate_environment",
                "technology": "technology_ai", "crime": "politics_society",
                "culture-and-society": "history_geography", "online": "streamer_viral_commentary",
                "news": "world_news", "conflict": "world_news", "immigration": "politics_society"}
            for link in page.links:
                video = canonical_video(link)
                if not video:
                    continue
                platform, vid, url = video
                key = platform + "_" + vid
                evidence = {"url": article, "title": page.title.strip(), "retrieved_at": now()}
                if key in rows:
                    if article not in {e["url"] for e in rows[key]["factcheck_references"]}:
                        rows[key]["factcheck_references"].append(evidence)
                    continue
                rows[key] = {"video_id": vid, "platform": platform, "url": url,
                    "source_handle": None, "source_kind": "factcheck_linked_poster",
                    "sampling_category": category_map.get(category, "world_news"),
                    "factcheck_topic": category, "category_reviewed": False,
                    "label": "unreviewed", "link_role": "needs_review",
                    "discovery_route": "factcheck_article", "discovered_at": now(),
                    "factcheck_references": [evidence]}
            print(f"{i+1}/{len(article_urls)} articles; {len(rows)} unique video leads", flush=True)
        except requests.RequestException as e:
            append(DATA / "factcheck_errors.jsonl", {"url": article, "error": str(e)})
        write_jsonl(DATA / "factcheck_candidates.jsonl", list(rows.values()))
        time.sleep(1)
    print(json.dumps({"articles": len(article_urls), "video_leads": len(rows)}))


if __name__ == "__main__":
    main()
