"""Fireworks-only inference with resumable request receipts; no credential logging."""
import hashlib
import json
import os
import time
import threading
import random
import uuid
from pathlib import Path
import requests
from dotenv import load_dotenv
from jsonschema import validate
from collect import ROOT, DATA, now, append

BASE_URL = "https://api.fireworks.ai/inference/v1"
REQUEST_LIMIT = threading.BoundedSemaphore(16)


def set_request_limit(count):
    global REQUEST_LIMIT
    REQUEST_LIMIT = threading.BoundedSemaphore(count)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def load(path):
    return json.loads(path.read_text())


class Fireworks:
    def __init__(self, env_file=None):
        load_dotenv(env_file or ROOT / '.env', override=False)
        key = os.environ.get('FIREWORKS_API_KEY')
        if not key:
            raise RuntimeError('FIREWORKS_API_KEY is missing; configure it locally, never in source code.')
        self.session = requests.Session()
        self.session.headers.update({'Authorization': 'Bearer ' + key})
        self.root = DATA / 'labeling' / 'api'

    def fork(self):
        return Fireworks()

    def models(self):
        response = self.session.get(BASE_URL + '/models', timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise RuntimeError(f'Fireworks model discovery HTTP {response.status_code}')
        return response.json()

    def json(self, model, system, content, schema, run_id, temperature=0.6, max_tokens=16384,
             reasoning_effort=None, max_output_limit=65536):
        body = {'model': model, 'messages': [
            {'role': 'system', 'content': system + '\nJSON schema:\n' + json.dumps(schema)},
            {'role': 'user', 'content': content}], 'temperature': temperature,
            'max_tokens': max_tokens,
            'response_format': {'type': 'json_schema', 'json_schema': {'name': 'annotation', 'schema': schema}}}
        if reasoning_effort is not None:
            body['reasoning_effort'] = reasoning_effort
        # run_id participates in the cache key so independent rounds are never deduplicated.
        fingerprint = digest({'body': body, 'run_id': run_id})
        receipt_path = self.root / (fingerprint + '.json')
        retry_path = self.root / (fingerprint + '.retry.json')
        if receipt_path.exists():
            receipt = load(receipt_path)
            validate(receipt['result'], schema)
            return receipt['result'], fingerprint
        if retry_path.exists():
            return self.json(model, system, content, schema, run_id, temperature,
                             load(retry_path)['max_tokens'], reasoning_effort, max_output_limit)
        for attempt in range(4):
            try:
                with REQUEST_LIMIT:
                    response = self.session.post(BASE_URL + '/chat/completions', json=body,
                                                 timeout=(20, 600), allow_redirects=False)
            except (requests.Timeout, requests.ConnectionError):
                if attempt == 3:
                    raise RuntimeError('Fireworks network timeout/connection failure; retry budget exhausted') from None
                time.sleep(min(30, 2 ** (attempt + 1)) + random.random())
                continue
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            delay = response.headers.get('Retry-After', '')
            delay = min(60, float(delay)) if delay.replace('.', '', 1).isdigit() else min(30, 2 ** (attempt + 1))
            time.sleep(delay + random.random())
        if response.status_code != 200:
            raise RuntimeError(f'Fireworks inference HTTP {response.status_code}; response body withheld')
        data = response.json()
        usage = data.get('usage', {})
        choice = data['choices'][0]
        append(self.root / 'usage.jsonl', {'at': now(), 'model': model, 'request_id': data.get('id'),
            'run_id': run_id, 'fingerprint': fingerprint, 'usage': usage,
            'finish_reason': choice.get('finish_reason')})
        if choice.get('finish_reason') == 'length' and max_tokens < max_output_limit:
            larger = min(max_output_limit, max_tokens * 2)
            save(retry_path, {'max_tokens': larger})
            return self.json(model, system, content, schema, run_id, temperature, larger,
                             reasoning_effort, max_output_limit)
        if choice.get('finish_reason') != 'stop':
            raise RuntimeError(f'Incomplete Fireworks answer: {choice.get("finish_reason")} for {run_id}')
        result = json.loads(choice['message']['content'])
        validate(result, schema)
        save(receipt_path, {'request_id': data.get('id'), 'at': now(), 'model': data.get('model', model),
            'requested_model': model, 'run_id': run_id, 'input_sha256': digest(body),
            'temperature': temperature, 'usage': usage, 'result': result})
        return result, fingerprint
