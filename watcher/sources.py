from __future__ import annotations

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


_LI_ID_RE = re.compile(r'<li id="([^"]+)"')
_TIME_RE = re.compile(r"<time[^>]*>\s*([^<]+?)\s*</time>")
_HEADING_RE = re.compile(r"<h[1-4][^>]*>(.*?)</h[1-4]>", re.S)
_ARTICLE_RE = re.compile(r"<article\b")
_TAG_RE = re.compile(r"""<(?:[^>"']|"[^"]*"|'[^']*')*>""")
_MAX_ENTRIES = 40


def _plain_text(fragment: str) -> str:
    no_tags = _TAG_RE.sub(" ", fragment)
    return " ".join(html_utils.unescape(no_tags).split())


def fetch_changelog_entries(cfg: Config) -> list[Post]:
    page = http_get(cfg.changelog_url)
    marks = list(_LI_ID_RE.finditer(page))
    entries: list[Post] = []
    spans = []
    for index, mark in enumerate(marks):
        end = marks[index + 1].start() if index + 1 < len(marks) else len(page)
        spans.append((mark.group(1), page[mark.start():end]))
    for li_id, span in spans:
        if _ARTICLE_RE.search(span) is None or len(entries) >= _MAX_ENTRIES:
            continue
        time_match = _TIME_RE.search(span)
        heading_match = _HEADING_RE.search(span)
        article_match = _ARTICLE_RE.search(span)
        body_html = span[article_match.start():span.find("</article>",
                                                        article_match.start())]
        date = _plain_text(time_match.group(1)) if time_match else ""
        title = _plain_text(heading_match.group(1)) if heading_match else "Changelog update"
        body = _plain_text(body_html)
        if not body:
            continue
        entries.append(Post(
            key=f"changelog:{li_id}",
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
