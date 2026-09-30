"""Tiny in-memory cache, cleared whenever data or the model changes."""
import time

_frames = {}
_state = {"bundle": None}


def get_frame(key, ttl, build):
    hit = _frames.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = build()
    _frames[key] = (time.time(), value)
    return value


def get_bundle(loader):
    if _state["bundle"] is None:
        _state["bundle"] = loader()
    return _state["bundle"]


def clear():
    _frames.clear()
    _state["bundle"] = None
