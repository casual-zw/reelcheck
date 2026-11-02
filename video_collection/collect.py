#!/usr/bin/env python3
"""Public short-video discovery and resumable local downloads. No API key needed."""
import argparse
import collections
import hashlib
import json
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def now():
    return datetime.now(timezone.utc).isoformat()


def read_jsonl(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def append(path, row):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    temp.replace(path)


def base_command():
    return [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-warnings",
            "--socket-timeout", "20", "--retries", "1", "--extractor-retries", "1",
            "--js-runtimes", "node", "--no-cache-dir"]


def discover(args):
    sources = json.loads((ROOT / "sources.json").read_text())
    if args.source:
        sources = [s for s in sources if s["handle"] == args.source]
    for source in sources:
        handle = source["handle"]
        cache = DATA / "discovery" / (handle + ".jsonl")
        if cache.exists() and not args.refresh:
            print(f"cached {handle}", flush=True)
            continue
        url = f"https://www.youtube.com/@{handle}/shorts"
        command = base_command() + ["--flat-playlist", "--playlist-end", str(args.per_source), "--dump-json", url]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=120)
            entries = [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]
            rows = [{"video_id": e["id"], "platform": "youtube", "url": e.get("url"),
                     "title": e.get("title"), "source_name": source["name"],
                     "source_handle": handle, "source_kind": source["kind"],
                     "source_url": url, "channel_id": e.get("playlist_channel_id"),
                     "sampling_category": source["category"], "category_reviewed": False,
                     "label": "unreviewed", "discovered_at": now(),
                     "discovery_route": "channel_shorts", "duration": e.get("duration")}
                    for e in entries if e.get("id")]
            if rows:
                write_jsonl(cache, rows)
            append(DATA / "discovery_log.jsonl", {"source": handle, "count": len(rows),
                   "returncode": result.returncode, "error": result.stderr[-1500:], "at": now()})
            print(f"{handle}: {len(rows)} candidates", flush=True)
        except subprocess.TimeoutExpired:
            append(DATA / "discovery_log.jsonl", {"source": handle, "error": "timeout", "at": now()})
            print(f"{handle}: timed out", flush=True)
        time.sleep(1)
    pool, seen = [], set()
    for path in sorted((DATA / "discovery").glob("*.jsonl")):
        for row in read_jsonl(path):
            key = (row["platform"], row["video_id"])
            if key not in seen:
                pool.append(row)
                seen.add(key)
    write_jsonl(DATA / "candidates.jsonl", pool)
    print(f"Unique candidates: {len(pool)}")


def select(args):
    """Round-robin categories and creators, with deterministic shuffle per creator."""
    leads = read_jsonl(DATA / "factcheck_candidates.jsonl")[:min(args.factcheck_count, args.count)]
    lead_ids = {(r["platform"], r["video_id"]) for r in leads}
    groups = collections.defaultdict(lambda: collections.defaultdict(list))
    for row in read_jsonl(DATA / "candidates.jsonl"):
        if (row["platform"], row["video_id"]) in lead_ids:
            continue
        groups[row["sampling_category"]][row["source_handle"]].append(row)
    rng = random.Random(args.seed)
    queues = {}
    for category, channels in sorted(groups.items()):
        for rows in channels.values():
            rng.shuffle(rows)
        queue = []
        while any(channels.values()):
            for channel in sorted(channels):
                if channels[channel]:
                    queue.append(channels[channel].pop())
        queues[category] = collections.deque(queue)
    chosen = []
    broad_count = args.count - len(leads)
    while len(chosen) < broad_count and any(queues.values()):
        for category in sorted(queues):
            if queues[category] and len(chosen) < broad_count:
                chosen.append(queues[category].popleft())
    # Interleave evidence leads so a small pilot exercises both acquisition routes.
    for i, lead in enumerate(leads):
        chosen.insert(min(2 + i * 20, len(chosen)), lead)
    write_jsonl(DATA / "selected.jsonl", chosen)
    print(json.dumps({"selected": len(chosen), "categories": dict(collections.Counter(r["sampling_category"] for r in chosen)),
                      "known_creators": len(set(r["source_handle"] for r in chosen if r.get("source_handle"))),
                      "evidence_leads": len(leads)}, indent=2))


def media_file(key):
    files = [p for p in (DATA / "videos").glob(key + ".*") if p.suffix in {".mp4", ".webm", ".mkv", ".mov"}]
    return files[0] if files else None


def ffmpeg():
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def validate_video(path):
    # Decode both audio and video; a nonzero file alone is not proof of success.
    result = subprocess.run([ffmpeg(), "-v", "error", "-xerror", "-i", str(path),
                             "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    return result.returncode == 0, result.stderr[-1000:]


def download(args):
    rows = read_jsonl(Path(args.manifest))
    success = {r["key"]: r for r in read_jsonl(DATA / "downloads.jsonl") if r["status"] == "downloaded"}
    attempted = 0
    consecutive_failures = 0
    for row in rows:
        key = row["platform"] + "_" + row["video_id"]
        if key in success and media_file(key):
            continue
        if attempted >= args.limit:
            break
        attempted += 1
        output = str(DATA / "videos" / (key + ".%(ext)s"))
        command = base_command() + ["--no-playlist", "--write-info-json",
            "--match-filters", "duration >= 10 & duration <= 180 & !is_live",
            "-f", "bv*[height<=480]+ba/b[height<=480]/b", "--merge-output-format", "mp4",
            "--ffmpeg-location", ffmpeg(), "-o", output, row["url"]]
        started = now()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=240)
            path = media_file(key)
            info_path = DATA / "videos" / (key + ".info.json")
            info = json.loads(info_path.read_text()) if info_path.exists() else {}
            valid, error = validate_video(path) if path else (False, "No media file")
            duration = info.get("duration")
            valid = valid and result.returncode == 0 and duration is not None and 10 <= duration <= 180
            record = dict(row, key=key, collected_at=started, status="downloaded" if valid else "failed",
                          duration=duration, upload_date=info.get("upload_date"),
                          title=info.get("title") or row.get("title"),
                          source_handle=info.get("uploader_id") or row.get("source_handle"),
                          source_name=info.get("uploader") or row.get("source_name"),
                          channel_id=info.get("channel_id") or row.get("channel_id"),
                          license=info.get("license"), language=info.get("language"),
                          language_reviewed=False, returncode=result.returncode)
            if valid:
                with path.open("rb") as media:
                    digest = hashlib.file_digest(media, "sha256").hexdigest()
                record.update(path=str(path.relative_to(ROOT)), bytes=path.stat().st_size, sha256=digest)
                success[key] = record
                consecutive_failures = 0
            else:
                record["error"] = (result.stderr + result.stdout + error)[-2500:]
                consecutive_failures += 1
        except (subprocess.TimeoutExpired, ValueError) as e:
            record = dict(row, key=key, status="failed", collected_at=started, error=str(e))
            consecutive_failures += 1
        append(DATA / "downloads.jsonl", record)
        print(f"{attempted}/{args.limit} {key}: {record['status']}", flush=True)
        if consecutive_failures >= 5:
            print("Stopping after five consecutive failures; inspect data/downloads.jsonl before retrying.")
            break
        time.sleep(args.delay)


def report(args):
    latest = {r["key"]: r for r in read_jsonl(DATA / "downloads.jsonl")}
    good = [r for r in latest.values() if r["status"] == "downloaded" and media_file(r["key"])]
    result = {"at": now(), "candidate_count": len(read_jsonl(DATA / "candidates.jsonl")),
              "selected_count": len(read_jsonl(DATA / "selected.jsonl")), "verified_downloads": len(good),
              "failed": sum(r["status"] == "failed" for r in latest.values()),
              "bytes": sum(r["bytes"] for r in good),
              "categories": dict(collections.Counter(r["sampling_category"] for r in good)),
              "creators": len(set(r.get("channel_id") or r.get("source_handle") for r in good
                                  if r.get("channel_id") or r.get("source_handle"))),
              "labels": dict(collections.Counter(r["label"] for r in good))}
    DATA.mkdir(exist_ok=True)
    (DATA / "report.json").write_text(json.dumps(result, indent=2) + "\n")
    write_jsonl(DATA / "downloaded_manifest.jsonl", good)
    print(json.dumps(result, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("discover")
    d.add_argument("--per-source", type=int, default=80)
    d.add_argument("--source")
    d.add_argument("--refresh", action="store_true")
    d.set_defaults(func=discover)
    s = sub.add_parser("select")
    s.add_argument("--count", type=int, default=1000)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--factcheck-count", type=int, default=50,
                   help="Reserve up to this many places for original-video leads linked by fact-checkers")
    s.set_defaults(func=select)
    d = sub.add_parser("download")
    d.add_argument("--manifest", default=str(DATA / "selected.jsonl"))
    d.add_argument("--limit", type=int, default=1000, help="Maximum new attempts in this run")
    d.add_argument("--delay", type=float, default=2)
    d.set_defaults(func=download)
    r = sub.add_parser("report")
    r.set_defaults(func=report)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
