"""
In-process, in-memory TTL cache for the 6 legacy HR table fetches.

CONFIRMED WITH ECHAN (2026-07-xx): a few minutes of staleness is
acceptable. TTL below defaults to 10 minutes (within Echan's stated
5-15 min tolerance) - not a fixed system rule, easy to change.

WHY THIS LAYER EXISTS: every one of the 6 legacy APIs ignores its
documented filter param entirely and always returns its FULL table (see
PROJECT_HANDOFF.md Section 4). Every employee's PDF request was
therefore re-fetching the ENTIRE primary table (~23K rows) plus all 5
secondary tables from scratch, even though the table content is
identical no matter which employee is asking. This cache is keyed by
ENDPOINT, not by employee - one cache entry serves every employee's
request until it expires.

FAILURE HANDLING: only successful fetches are cached. If a refresh
attempt raises, the exception propagates to the caller and the
PREVIOUS (now-stale) cached value is left untouched - a transient
legacy-API failure should not wipe out data that was working, and
should not get cached as if it were a valid result either.

CONCURRENCY: an asyncio.Lock per cache key prevents a "stampede" -
multiple concurrent requests hitting an expired entry at the same
moment would otherwise all independently re-fetch the same table at
once. The lock ensures only one of them actually fetches; the others
wait, then reuse that result.

DEPLOYMENT NOTE: this is a simple in-process dict, not shared across
multiple worker processes or server instances. Deployment target is
still undecided (PROJECT_HANDOFF.md Section 9 item 5) - if this ever
runs as multiple uvicorn workers or multiple machines, each process
keeps its own separate cache (correct, but each independently re-fetches
on its own timer - wasteful, not broken). Revisit with a shared cache
(e.g. Redis) if/when that becomes the deployment model - not worth
solving before the deployment model itself is decided.

DEV NOTE: uvicorn's --reload spawns a fresh process on every code
change, which resets this cache to empty. Expected, not a bug.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

TTL_SECONDS = 10 * 60  # 10 minutes - within Echan's confirmed 5-15 min tolerance


class _CacheEntry:
    __slots__ = ("data", "fetched_at", "lock")

    def __init__(self) -> None:
        self.data = None
        self.fetched_at: float = 0.0
        self.lock = asyncio.Lock()


_cache: dict[str, _CacheEntry] = {}


def _get_entry(key: str) -> _CacheEntry:
    if key not in _cache:
        _cache[key] = _CacheEntry()
    return _cache[key]


async def get_cached_table(key: str, fetch_fn: Callable[[], Awaitable[dict]]) -> dict:
    """Return the cached raw table envelope for `key`, re-fetching via
    `fetch_fn` if missing or older than TTL_SECONDS. `fetch_fn` is a
    zero-arg async callable that performs the actual HTTP GET and
    returns the parsed envelope dict - this module has no knowledge of
    URLs or HTTP, it only manages the cache/TTL/stampede-lock mechanics.
    If fetch_fn raises, the exception propagates and any previous cached
    value for this key is left untouched (see module docstring)."""
    entry = _get_entry(key)

    now = time.monotonic()
    if entry.data is not None and (now - entry.fetched_at) < TTL_SECONDS:
        logger.info("Cache hit for %s (age %.1fs)", key, now - entry.fetched_at)
        return entry.data

    async with entry.lock:
        now = time.monotonic()
        if entry.data is not None and (now - entry.fetched_at) < TTL_SECONDS:
            logger.info("Cache hit for %s after lock wait (age %.1fs)", key, now - entry.fetched_at)
            return entry.data

        logger.info("Cache miss/expired for %s, fetching fresh", key)
        entry.data = await fetch_fn()
        entry.fetched_at = time.monotonic()
        return entry.data