from __future__ import annotations

import hashlib
import html as html_utils
import re

from .config import Config
from .fetch import get_json, http_get
from .model import Post


def fetch_x_posts(cfg: Config) -> list[Post]:
    url = cfg.dayclaw_url.format(handle=cfg.handle)
    data = get_json(url)
    items = data.get("items") or []
    posts: list[Post] = []
    for item in items:
        external_id = str(item.get("external_id") or item.get("id") or "")
        text = item.get("content") or item.get("title") or ""
        if not external_id or not text:
            continue
        metadata = item.get("metadata") or {}
        posts.append(Post(
            key=f"dayclaw:{external_id}",
            source="x",
            title=" ".join(text.split()),
            body=html_utils.unescape(text),
            url=item.get("url") or f"https://x.com/{cfg.handle}/status/{external_id}",
            created_at=item.get("published_at") or "",
            is_reply=bool(metadata.get("is_reply") or metadata.get("isReply")),
        ))
    return posts


_ENTRY_RE = re.compile(
    r"<time[^>]*>\s*([^<]+?)\s*</time>"
    r".*?<h[1-4][^>]*>(.*?)</h[1-4]>"
    r".*?<article\b.*?</article>",
    re.S,
)
_TAG_RE = re.compile(r"<[^>]+>")
_MAX_ENTRIES = 40


def _plain_text(fragment: str) -> str:
    no_tags = _TAG_RE.sub(" ", fragment)
    return " ".join(html_utils.unescape(no_tags).split())


def fetch_changelog_entries(cfg: Config) -> list[Post]:
    page = http_get(cfg.changelog_url)
    entries: list[Post] = []
    for match in list(_ENTRY_RE.finditer(page))[:_MAX_ENTRIES]:
        date = _plain_text(match.group(1))
        title = _plain_text(match.group(2)) or "Changelog update"
        body = _plain_text(match.group(0)[match.group(0).find("<article"):])
        if not body:
            continue
        fingerprint = hashlib.sha1(body[:240].casefold().encode()).hexdigest()
        entries.append(Post(
            key=f"changelog:{fingerprint[:24]}",
            source="changelog",
            title=title,
            body=body,
            url=cfg.changelog_url,
            created_at=date,
        ))
    return entries


def collect(cfg: Config) -> list[Post]:
    posts: list[Post] = []
    try:
        posts.extend(fetch_x_posts(cfg))
    except Exception as error:
        print(f"[warn] X/Dayclaw source failed: {error}")
    if cfg.watch_changelog:
        try:
            posts.extend(fetch_changelog_entries(cfg))
        except Exception as error:
            print(f"[warn] changelog source failed: {error}")
    return posts
