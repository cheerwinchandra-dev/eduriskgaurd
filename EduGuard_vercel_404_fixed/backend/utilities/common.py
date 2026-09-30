"""Shared paths, configuration and logging for EduGuard."""
import copy
import json
import logging
import os
import re
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_HERE = Path(__file__).resolve()
_BACKEND_CANDIDATE = _HERE.parent.parent
if _BACKEND_CANDIDATE.name == "backend" and (_BACKEND_CANDIDATE / "config.json").exists():
    BACKEND = _BACKEND_CANDIDATE
    _DEFAULT_ROOT = BACKEND.parent
else:
    _DEFAULT_ROOT = _HERE.parents[2]
    BACKEND = _DEFAULT_ROOT / "backend"
ROOT = Path(os.environ.get("EDUGUARD_ROOT") or _DEFAULT_ROOT)
BACKEND = ROOT / "backend"
IS_VERCEL = str(os.environ.get("VERCEL", "")).lower() in {"1", "true", "yes"}
RUNTIME_ROOT = Path(os.environ.get("EDUGUARD_RUNTIME_DIR") or ("/tmp/eduguard" if IS_VERCEL else ROOT))
SOURCE_CONFIG_PATH = BACKEND / "config.json"
CONFIG_PATH = RUNTIME_ROOT / "config.json" if IS_VERCEL else SOURCE_CONFIG_PATH
DATA_DIR = RUNTIME_ROOT / "data" if IS_VERCEL else BACKEND / "data"
MODEL_DIR = RUNTIME_ROOT / "models" / "ai-model" if IS_VERCEL else ROOT / "models" / "ai-model"
LOG_DIR = RUNTIME_ROOT / "logs" if IS_VERCEL else ROOT / "logs"

if IS_VERCEL:
    # Vercel deployments are immutable. Copy the bundled config into /tmp on cold start
    # so settings and generated runtime state remain writable during the function lifetime.
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not CONFIG_PATH.exists() and SOURCE_CONFIG_PATH.exists():
            CONFIG_PATH.write_text(SOURCE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        # load_config() still falls back to DEFAULT_CONFIG below.
        pass

DEFAULT_CONFIG = {
    "app_name": "EduGuard",
    "version": "1.0.0",
    "host": "127.0.0.1",
    "port": 8765,
    "demo": {"students": 1800, "seed": 42},
    "risk": {"moderate_threshold": 0.10, "elevated_threshold": 0.25},
    "alerts": {
        "weekly_capacity": 40,
        "cooldown_days": 7,
        "max_data_age_days": 7,
        "rise_alert_threshold": 0.10,
        "dismiss_days": 30,
    },
    "fairness": {
        "min_group_size": 30,
        "calibration_gap_threshold": 0.05,
        "fpr_gap_threshold": 0.03,
        "fnr_gap_threshold": 0.10,
    },
    "assistant": {
        "enabled": True,
        "provider": "auto",            # auto | gemini | ollama | templates
        "gemini_mode": "off",          # off | aggregate | case
        "gemini_model": "gemini-3.8-flash",
        "gemini_attested": False,      # admin confirmed the key belongs to a paid, billing-enabled project
        "ollama_host": "http://127.0.0.1:11434",
        "model": "llama3.2:1b",
        "timeout_seconds": 45,
    },
}

# Settings an administrator may change from the UI (section -> allowed keys).
EDITABLE = {
    "risk": {"moderate_threshold", "elevated_threshold"},
    "alerts": {"weekly_capacity", "cooldown_days", "max_data_age_days", "rise_alert_threshold", "dismiss_days"},
    "assistant": {"enabled", "model", "provider", "gemini_mode", "gemini_model", "gemini_attested"},
}


def _merge(base, extra):
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config():
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            _merge(cfg, json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return cfg


def save_config(changes: dict):
    """Apply only whitelisted changes and write config.json."""
    cfg = load_config()
    for section, values in (changes or {}).items():
        allowed = EDITABLE.get(section, set())
        for key, value in (values or {}).items():
            if key in allowed:
                cfg[section][key] = value
    risk = cfg["risk"]
    if not 0 < risk["moderate_threshold"] < risk["elevated_threshold"] < 1:
        raise ValueError("Thresholds must satisfy 0 < moderate < elevated < 1.")
    a = cfg["assistant"]
    if a["provider"] not in ("auto", "gemini", "ollama", "templates"):
        raise ValueError("Choose a provider from the list.")
    if a["gemini_mode"] not in ("off", "aggregate", "case"):
        raise ValueError("Choose a data-sharing level from the list.")
    if not re.fullmatch(r"[A-Za-z0-9._\-]{3,80}", str(a["gemini_model"])):
        raise ValueError("That doesn't look like a valid Gemini model name.")
    if a["gemini_mode"] == "case" and not a["gemini_attested"]:
        raise ValueError("Confirm that the Gemini key belongs to a paid, billing-enabled project before sharing case summaries.")
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return cfg


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_ts(value):
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


_configured = False


def get_logger(name="eduguard"):
    global _configured
    if not _configured:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        root = logging.getLogger("eduguard")
        root.setLevel(logging.INFO)
        root.addHandler(handler)
        if sys.stderr is not None and sys.stderr.isatty():  # console output only when run by hand
            console = logging.StreamHandler()
            console.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            root.addHandler(console)
        _configured = True
    return logging.getLogger(name if name.startswith("eduguard") else f"eduguard.{name}")


def clean(obj):
    """Make pandas/numpy results JSON-safe (NaN and inf become null)."""
    import math

    import numpy as np

    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if isinstance(obj, np.generic):
        obj = obj.item()
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    return obj


# ---------------------------------------------------------------- secrets (Gemini API key)
SECRETS_PATH = DATA_DIR / "secrets.json"


def _read_secrets():
    try:
        return json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_gemini_key():
    """The environment variable wins over the saved key."""
    env = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    return env or (_read_secrets().get("gemini_api_key") or "").strip() or None


def key_source():
    if (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip():
        return "environment"
    return "saved" if _read_secrets().get("gemini_api_key") else None


def set_gemini_key(key):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    secrets = _read_secrets()
    if key:
        secrets["gemini_api_key"] = key
    else:
        secrets.pop("gemini_api_key", None)
    SECRETS_PATH.write_text(json.dumps(secrets), encoding="utf-8")
    try:
        os.chmod(SECRETS_PATH, 0o600)  # best effort; Windows ignores most of this
    except OSError:
        pass


def mask_key(key):
    return f"{key[:4]}...{key[-4:]}" if key and len(key) > 12 else ""


def redact(text):
    """Never let the API key appear in an error message or a log line."""
    key = get_gemini_key()
    return text.replace(key, "[hidden key]") if key and text else text
