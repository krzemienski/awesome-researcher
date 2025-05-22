"""Validate that every URL returns a successful status to prevent dead links."""
from __future__ import annotations

import asyncio
from typing import Iterable

import httpx

async def _check(url: str, timeout: float = 2.0) -> bool:
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            r = await client.head(url)
            return r.status_code < 400
    except httpx.HTTPError:
        return False

async def validate_urls(urls: Iterable[str]) -> set[str]:
    tasks = [_check(u) for u in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    bad = {u for u, ok in zip(urls, results) if not ok}
    return bad
