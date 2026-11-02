"""Prepare the complete audio and two interleaved frame samples for each clip."""
import argparse
import hashlib
import os
import subprocess
import wave
from pathlib import Path
from collect import DATA, ROOT, ffmpeg, read_jsonl, now
from fireworks_client import load, save, digest

ASR_MODEL = 'mlx-community/whisper-large-v3-turbo'


def prepare(row):
    key = row['key']
    root = DATA / 'labeling' / 'media' / key
    source = (ROOT / row['path']).resolve()
    if not source.is_relative_to((DATA / 'videos').resolve()):
        raise ValueError('Video path must be inside data/videos')
    with source.open('rb') as f:
        video_hash = hashlib.file_digest(f, 'sha256').hexdigest()
    if video_hash != row['sha256']:
        raise ValueError(f'Video hash mismatch for {key}')
    config = {'video_sha256': video_hash, 'frame_fps': 1, 'max_width': 640, 'asr_model': ASR_MODEL}
    target = root / 'prepared.json'
    if target.exists() and load(target).get('config_hash') == digest(config):
        saved = load(target)
        if all((ROOT / f['path']).exists() for f in saved['frames']) and (root / 'transcript.json').exists():
            return saved
    root.mkdir(parents=True, exist_ok=True)
    frames_dir = root / 'frames'
    frames_dir.mkdir(exist_ok=True)
    subprocess.run([ffmpeg(), '-v', 'error', '-y', '-i', str(source),
        '-vf', "fps=1:start_time=0,scale='min(640,iw)':-2", '-q:v', '6',
        str(frames_dir / '%04d.jpg')], check=True, capture_output=True)
    frames = [{'seconds': i, 'path': str(p.relative_to(ROOT))}
              for i, p in enumerate(sorted(frames_dir.glob('*.jpg')))]
    if not frames or len(frames) > 181:
        raise ValueError('Unexpected number of sampled frames')
    audio_path = root / 'audio.wav'
    subprocess.run([ffmpeg(), '-v', 'error', '-y', '-i', str(source), '-vn',
        '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(audio_path)], check=True, capture_output=True)
    os.environ['HF_HOME'] = str(DATA / 'labeling' / 'model_cache')
    os.environ['NUMBA_CACHE_DIR'] = str(DATA / 'labeling' / 'numba_cache')
    import numpy as np
    import mlx_whisper
    with wave.open(str(audio_path), 'rb') as f:
        audio = np.frombuffer(f.readframes(f.getnframes()), np.int16).astype(np.float32) / 32768.0
    transcript = mlx_whisper.transcribe(audio, path_or_hf_repo=ASR_MODEL,
        verbose=None, temperature=0.0, condition_on_previous_text=False)
    # Keep speech text, timings and diagnostics, never claim a human checked the ASR.
    transcript = {'text': transcript['text'], 'language': transcript.get('language'),
        'segments': [{k: s.get(k) for k in ['start', 'end', 'text', 'avg_logprob', 'no_speech_prob']}
                     for s in transcript.get('segments', [])],
        'model': ASR_MODEL, 'automatic': True, 'human_verified': False, 'at': now()}
    save(root / 'transcript.json', transcript)
    result = {'key': key, 'config_hash': digest(config), **config, 'frames': frames,
        'duration': row['duration'], 'transcript_sha256': digest(transcript),
        'frame_sampling_note': '1 FPS approximation; each judge sees one alternating 0.5 FPS sample.',
        'source_resolution': 'Original collected media; small text may be unreadable.', 'at': now()}
    save(target, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key')
    parser.add_argument('--limit', type=int, default=1000)
    args = parser.parse_args()
    rows = read_jsonl(DATA / 'downloaded_manifest.jsonl')
    rows.sort(key=lambda r: (r['key'] not in {'youtube_nPg--LTa31w', 'youtube_1TuLprcGmSI'}, r['key']))
    if args.key:
        rows = [r for r in rows if r['key'] == args.key]
    for i, row in enumerate(rows[:args.limit]):
        result = prepare(row)
        print(f"{i+1}/{min(args.limit, len(rows))} {row['key']}: {len(result['frames'])} frames + full transcript", flush=True)


if __name__ == '__main__':
    main()
