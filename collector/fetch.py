"""Polite HTTP fetching: honest user agent, robots.txt respected, per-host delay."""
from __future__ import annotations

import threading
import time
import urllib.robotparser
from urllib.parse import urlsplit

import requests

UA = "PositionFinderBot/0.1 (+https://github.com/Positionfinder/Position_Finder)"
ROBOTS_AGENT = "PositionFinderBot"
PER_HOST_DELAY = 2.0  # seconds between requests to the same host
TIMEOUT = 30

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "en,es;q=0.8,ca;q=0.6"})
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_last_hit: dict[str, float] = {}
_lock = threading.Lock()
_host_locks: dict[str, threading.Lock] = {}


def _host_lock(host: str) -> threading.Lock:
    with _lock:
        return _host_locks.setdefault(host, threading.Lock())


def _wait(host: str) -> None:
    with _lock:
        last = _last_hit.get(host, 0.0)
        now = time.monotonic()
        delay = max(0.0, last + PER_HOST_DELAY - now)
        _last_hit[host] = now + delay
    if delay:
        time.sleep(delay)


def robots_for(url: str) -> urllib.robotparser.RobotFileParser | None:
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    with _host_lock(parts.netloc):
        if base in _robots:
            return _robots[base]
        rp = urllib.robotparser.RobotFileParser()
        try:
            _wait(parts.netloc)
            r = _session.get(base + "/robots.txt", timeout=TIMEOUT)
            if r.status_code in (401, 403):
                rp.disallow_all = True
            elif r.status_code >= 400:
                rp.allow_all = True
            else:
                rp.parse(r.text.splitlines())
        except requests.RequestException:
            rp = None  # unreachable; fetch() will fail anyway
        _robots[base] = rp
        return rp


def allowed(url: str) -> bool:
    rp = robots_for(url)
    return True if rp is None else rp.can_fetch(ROBOTS_AGENT, url)


class Blocked(Exception):
    """URL disallowed by robots.txt."""


def fetch(url: str) -> requests.Response:
    if not allowed(url):
        raise Blocked(url)
    host = urlsplit(url).netloc
    _wait(host)
    r = _session.get(url, timeout=TIMEOUT, allow_redirects=True)
    if r.url != url and not allowed(r.url):
        raise Blocked(r.url)
    r.raise_for_status()
    if not r.encoding or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding
    return r
