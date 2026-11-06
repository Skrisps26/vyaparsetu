"""Public-page fetching via a maintained SSRF-protected client, never a URL proxy."""
from __future__ import annotations

import asyncio
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import safehttpx

USER_AGENT = "VyaparSetu/0.1 (https://github.com/Skrisps26/vyaparsetu)"
MAX_HTML_BYTES = 2_000_000


def public_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return bool(parts.hostname) and parts.scheme in {"http", "https"} and not parts.username and not parts.password and parts.port in {None, 80, 443}
    except ValueError:
        return False


async def _get(url: str):
    if not public_url(url):
        raise ValueError("Only public HTTP(S) source links without credentials are supported")
    # No whitelist or transport escape hatch: safehttpx checks DNS and rebinding.
    response = await safehttpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=6)
    response.raise_for_status()
    if response.is_redirect:
        raise ValueError("Source redirects are not followed")
    if len(response.content) > MAX_HTML_BYTES:
        raise ValueError("Source is too large to inspect")
    return response


async def fetch_public_html(url: str) -> str:
    """Read only pages their publisher permits, bounded by a per-page deadline."""
    async with asyncio.timeout(9):
        parts = urlsplit(url)
        if not public_url(url):
            raise ValueError("Invalid public source URL")
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        robots_response = await _get(robots_url)
        robots = RobotFileParser()
        robots.parse(robots_response.text.splitlines())
        if not robots.can_fetch(USER_AGENT, url):
            raise ValueError("Publisher disallows automated reading")
        response = await _get(url)
        if "text/html" not in response.headers.get("content-type", ""):
            raise ValueError("Source is not an HTML product page")
        return response.text
