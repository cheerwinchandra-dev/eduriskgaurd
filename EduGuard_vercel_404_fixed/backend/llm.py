"""Language-model providers (Google Gemini and local Ollama).

The risk score always comes from the calibrated statistical model, never from a language model.
Language models are used only to explain, summarise and draft, and only within the data-sharing
level an administrator chose:

* aggregate: group-level statistics only (no individual student)
* case:      aggregate + de-identified, qualitative case summaries (no IDs, names, dates or numbers)
"""
import json
import re
import time

import requests

from .utilities.common import get_gemini_key, get_logger, load_config, redact

log = get_logger("llm")
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
_NOT_CHAT = ("tts", "image", "live", "audio", "embedding", "native", "veo", "imagen", "robotics", "computer-use")


class LLMError(Exception):
    """A problem worth showing to the user, already written in plain language."""


# ------------------------------------------------------------------ Gemini
def _explain_http(status, body):
    msg = ""
    try:
        msg = (json.loads(body).get("error") or {}).get("message", "")
    except (ValueError, AttributeError):
        pass
    if status == 400 and "api key" in msg.lower():
        return "Google rejected the API key. Check that it was copied completely."
    if status in (401, 403):
        return "Google refused the request. Check the API key and that the Gemini API is enabled for its project."
    if status == 404:
        return "That model isn't available for this key. Use Test connection to see the models you can use."
    if status == 429:
        return "Google's rate limit was reached. Wait a minute and try again."
    if status >= 500:
        return "Google's service had a temporary problem. Try again shortly."
    return "Google returned an error" + (f": {redact(msg)[:160]}" if msg else ".")


def _parse_gemini(data):
    if (data.get("promptFeedback") or {}).get("blockReason"):
        raise LLMError("Google's safety filter blocked this request.")
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMError("Google returned no answer.")
    cand = candidates[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        reason = cand.get("finishReason")
        if reason == "MAX_TOKENS":
            raise LLMError("The answer was cut short. Try again.")
        if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII"):
            raise LLMError("Google's safety filter withheld the answer.")
        raise LLMError("Google returned an empty answer.")
    return text


def gemini_generate(system, prompt, *, json_mode=False, max_tokens=4096, temperature=0.3, model=None, key=None):
    key = key or get_gemini_key()
    if not key:
        raise LLMError("No Gemini API key is saved.")
    model = (model or load_config()["assistant"]["gemini_model"]).replace("models/", "")
    config = {"temperature": temperature, "maxOutputTokens": max_tokens}
    if json_mode:
        config["responseMimeType"] = "application/json"
    body = {"systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": config}
    headers = {"Content-Type": "application/json", "x-goog-api-key": key}  # header, so the key never appears in a URL
    url = f"{GEMINI_BASE}/models/{model}:generateContent"

    last = None
    for attempt in range(2):
        try:
            r = requests.post(url, headers=headers, json=body, timeout=60)
        except requests.RequestException as exc:
            log.warning("Gemini request failed: %s", redact(str(exc))[:200])
            last = LLMError("Couldn't reach Google. Check the internet connection.")
            time.sleep(1.5)
            continue
        if r.status_code in (429, 500, 502, 503, 504) and attempt == 0:
            time.sleep(2)
            last = LLMError(_explain_http(r.status_code, r.text))
            continue
        if r.status_code != 200:
            raise LLMError(_explain_http(r.status_code, r.text))
        return _parse_gemini(r.json())
    raise last or LLMError("Google didn't answer.")


def list_models(key=None):
    """Chat-capable Gemini models this key can use, newest Flash first."""
    key = key or get_gemini_key()
    if not key:
        raise LLMError("No Gemini API key is saved.")
    try:
        r = requests.get(f"{GEMINI_BASE}/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=20)
    except requests.RequestException:
        raise LLMError("Couldn't reach Google. Check the internet connection.")
    if r.status_code != 200:
        raise LLMError(_explain_http(r.status_code, r.text))
    names = []
    for m in r.json().get("models", []):
        name = (m.get("name") or "").replace("models/", "")
        if name.startswith("gemini-") and "generateContent" in (m.get("supportedGenerationMethods") or []) \
                and not any(t in name for t in _NOT_CHAT):
            names.append(name)

    def rank(n):
        version = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        group = 0 if ("flash" in n and "lite" not in n) else 1 if "lite" in n else 2
        return (group, -(float(version.group(1)) if version else 0), n)

    return sorted(set(names), key=rank)


# ------------------------------------------------------------------ Ollama (local)
_ollama_cache = {"at": 0.0, "value": None}


def ollama_status(force=False):
    cfg = load_config()["assistant"]
    if not force and _ollama_cache["value"] and time.time() - _ollama_cache["at"] < 20:
        return _ollama_cache["value"]
    out = {"enabled": bool(cfg["enabled"]), "model": cfg["model"], "reachable": False, "model_ready": False, "host": cfg["ollama_host"]}
    if cfg["enabled"]:
        try:
            r = requests.get(f"{cfg['ollama_host']}/api/tags", timeout=2)
            r.raise_for_status()
            names = [m.get("name", "") for m in r.json().get("models", [])]
            out["reachable"] = True
            wanted = cfg["model"].split(":")[0]
            out["model_ready"] = any(n == cfg["model"] or n.split(":")[0] == wanted for n in names)
        except (requests.RequestException, ValueError):
            pass
    _ollama_cache.update(at=time.time(), value=out)
    return out


def ollama_generate(system, prompt, *, json_mode=False, max_tokens=800, temperature=0.3):
    cfg = load_config()["assistant"]
    payload = {"model": cfg["model"], "system": system, "prompt": prompt, "stream": False,
               "options": {"temperature": temperature, "num_predict": max_tokens}}
    if json_mode:
        payload["format"] = "json"
    try:
        r = requests.post(f"{cfg['ollama_host']}/api/generate", json=payload, timeout=cfg["timeout_seconds"])
        r.raise_for_status()
        text = (r.json().get("response") or "").strip()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Ollama request failed: %s", exc)
        raise LLMError("The local AI model didn't answer.")
    if not text:
        raise LLMError("The local AI model returned an empty answer.")
    return text


# ------------------------------------------------------------------ routing
def eligible(level):
    """Providers allowed to see data of this level, in order of preference."""
    a = load_config()["assistant"]
    if a["provider"] == "templates":
        return []
    out = []
    mode_ok = a["gemini_mode"] == "case" or (a["gemini_mode"] == "aggregate" and level == "aggregate")
    if a["provider"] in ("auto", "gemini") and get_gemini_key() and mode_ok:
        out.append("gemini")
    if a["provider"] in ("auto", "ollama") and a["enabled"] and ollama_status()["model_ready"]:
        out.append("ollama")
    return out


def generate(system, prompt, level, *, json_mode=False, max_tokens=2048, temperature=0.3):
    """Try each allowed provider in turn. Returns (text, provider) or raises LLMError."""
    providers = eligible(level)
    if not providers:
        raise LLMError("No AI provider is available for this. Connect Gemini or run Ollama in Settings.")
    last = None
    for name in providers:
        try:
            if name == "gemini":
                return gemini_generate(system, prompt, json_mode=json_mode, max_tokens=max(max_tokens, 2048), temperature=temperature), name
            return ollama_generate(system, prompt, json_mode=json_mode, max_tokens=max_tokens, temperature=temperature), name
        except LLMError as exc:
            log.info("%s unavailable: %s", name, exc)
            last = exc
    raise last
