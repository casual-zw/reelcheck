"""Small HTTP adapters with explicit configuration and no secret logging."""
import json
import os
import shlex
import time
import urllib.error
import urllib.request
from pathlib import Path

ENDPOINTS = {
    "fireworks": ("https://api.fireworks.ai/inference/v1/chat/completions", "FIREWORKS_API_KEY"),
    "anthropic": ("https://api.anthropic.com/v1/messages", "ANTHROPIC_API_KEY"),
    "openai": ("https://api.openai.com/v1/chat/completions", "OPENAI_API_KEY"),
}


def load_shell_exports(path):
    """Read only direct key exports. Never execute the user's shell configuration."""
    allowed = {name for _, name in ENDPOINTS.values()}
    for line in Path(path).expanduser().read_text().splitlines():
        if not any(line.strip().startswith("export " + name + "=") for name in allowed):
            continue
        try:
            parts = shlex.split(line.strip())
        except ValueError:
            raise ValueError("Could not parse a credential export; use KEY=value in a local .env instead") from None
        if len(parts) == 2:
            key, _, value = parts[1].partition("=")
            if key in allowed and value:
                os.environ[key] = value


def load_env(path):
    path = Path(path)
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:]
        key, sep, value = line.partition("=")
        if not sep or not key.strip().replace("_", "").isalnum():
            raise ValueError("Invalid .env line; use KEY=value without shell commands")
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key.strip(), value)


def call(config, messages):
    provider = config["provider"]
    endpoint, env_name = ENDPOINTS[provider]
    token = os.environ.get(env_name)
    if not token:
        raise ValueError(f"Missing {env_name}; put it in .env, never in chat")
    headers = {"Content-Type": "application/json"}
    body = {"model": config["model"], "messages": messages}
    if provider == "anthropic":
        headers.update({"x-api-key": token, "anthropic-version": "2023-06-01"})
        body["system"] = messages[0]["content"]
        body["messages"] = messages[1:]
        body["max_tokens"] = config["max_output_tokens"]
    else:
        headers["Authorization"] = "Bearer " + token
        body["max_tokens" if provider == "fireworks" else "max_completion_tokens"] = config["max_output_tokens"]
        body["response_format"] = {"type": "json_object"}
    # No temperature override: unsupported parameters must not silently trigger retries.
    for key, value in config.get("parameters", {}).items():
        if key in {"model", "messages", "system", "max_tokens", "max_completion_tokens", "stream"}:
            raise ValueError(f"Reserved provider parameter: {key}")
        body[key] = value
    request = urllib.request.Request(endpoint, json.dumps(body).encode(), headers, method="POST")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=config.get("timeout_s", 60)) as response:
            raw = json.load(response)
    except urllib.error.HTTPError as e:
        # Error bodies may echo submitted data; persist only status, never auth headers.
        return {"execution_status": "api_error", "http_status": e.code,
                "latency_s": time.monotonic()-started, "usage": None,
                "cost_usd": None, "output": None}
    except (TimeoutError, OSError):
        return {"execution_status": "transport_error", "latency_s": time.monotonic()-started,
                "usage": None, "cost_usd": None, "output": None}
    duration = time.monotonic()-started
    if provider == "anthropic":
        content = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
        finish = raw.get("stop_reason")
    else:
        choices = raw.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            return {"execution_status":"protocol_error", "latency_s":duration,
                    "usage":raw.get("usage"), "cost_usd":estimate_cost(raw.get("usage"),provider,config.get("pricing")), "output":None}
        choice = choices[0]
        content = choice.get("message", {}).get("content") or ""
        finish = choice.get("finish_reason")
    usage = raw.get("usage")
    status = "completed"
    if finish in {"length", "max_tokens"}:
        status = "truncated"
    try:
        output = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        output, status = None, "invalid_json" if status == "completed" else status
    return {"execution_status": status, "output": output, "raw_text": content,
            "latency_s": duration, "usage": usage, "finish_reason": finish,
            "resolved_model": raw.get("model"), "request_id": raw.get("id"),
            "cost_usd": estimate_cost(usage, provider, config.get("pricing"))}


def estimate_cost(usage, provider, pricing):
    if not usage or not pricing:
        return None
    if provider == "anthropic":
        inp, out = usage.get("input_tokens"), usage.get("output_tokens")
        if usage.get("cache_creation_input_tokens", 0) or usage.get("cache_read_input_tokens", 0):
            return None  # Do not silently omit cache billing.
    else:
        inp, out = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if inp is None or out is None:
        return None
    # Reasoning is already included in completion/output totals, not added twice.
    cached = usage.get("prompt_tokens_details", {}).get("cached_tokens", 0) or 0
    if not 0 <= cached <= inp:
        return None
    cached_rate = pricing.get("cached_input_per_million", pricing["input_per_million"])
    return ((inp-cached)*pricing["input_per_million"] + cached*cached_rate + out*pricing["output_per_million"])/1_000_000
