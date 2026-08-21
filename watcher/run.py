from __future__ import annotations

import time
from datetime import datetime, timezone

from . import notify, sources
from .config import Config
from .detect import score_text, should_alert
from .state import StateStore

MAX_ALERTS_PER_CYCLE = 5


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")


def log(message: str) -> None:
    print(f"[{_stamp()}] {message}", flush=True)


def check_once(cfg: Config, *, prime: bool = False, dry_run: bool = False) -> int:
    posts = sources.collect(cfg)
    if not posts:
        log("no posts fetched from any source; keeping previous state")
        return 0

    store = StateStore(cfg.state_file)
    baseline = store.fresh_file or prime
    findings = []

    for post in posts:
        if store.is_seen(post.key):
            continue
        score = score_text(post.body)
        if cfg.verbose:
            log(f"new {post.source} item, score {score.total} ({score.hits}): "
                f"{post.title[:70]}")
        store.mark_seen(post.key)
        if not cfg.include_replies and post.is_reply:
            continue
        if cfg.alert_all or should_alert(score, cfg.score_threshold):
            findings.append((post, score))

    if baseline:
        findings = []
        log(f"baseline recorded: {store.tracked_count()} items tracked, "
            "no alerts sent (first run / prime)")

    pushed = 0
    if len(findings) > MAX_ALERTS_PER_CYCLE:
        log(f"{len(findings)} findings, capping at {MAX_ALERTS_PER_CYCLE} "
            "pushes this cycle")
    for post, score in findings[:MAX_ALERTS_PER_CYCLE]:
        if dry_run:
            log(f"DRY-RUN would push: score {score.total} ({score.hits}) "
                f"{post.url}")
            continue
        results = notify.send_alert(cfg, post, score.total, score.hits)
        for ok, note in results:
            if not ok:
                log(f"DELIVERY FAILED {note}")
        if not results:
            log(f"finding scored {score.total} but no notification channel "
                "is configured (set NTFY_TOPIC etc.)")
        pushed += 1

    if not dry_run:
        store.save()
    log(f"cycle done: {len(posts)} fetched, {len(findings)} matched, "
        f"{pushed} pushed{' (dry-run)' if dry_run else ''}")
    return pushed


def run_loop(cfg: Config) -> None:
    interval = cfg.interval_min * 60
    channels = ", ".join(cfg.active_channels()) or "NONE (console only!)"
    log(f"loop started: every {cfg.interval_min} min, watching "
        f"@{cfg.handle}, channels: {channels}")
    while True:
        try:
            check_once(cfg)
        except KeyboardInterrupt:
            log("interrupted; bye")
            return
        except Exception as error:
            log(f"cycle crashed but loop continues: {error}")
        time.sleep(interval)
