from __future__ import annotations

import json
import smtplib
import ssl
from email.message import EmailMessage

from .config import Config
from .fetch import http_post
from .model import Post

SHORT_PREVIEW = 350
LONG_PREVIEW = 1200


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def format_alert(cfg: Config, post: Post, score_total: int, score_hits: str,
                 *, long: bool = False) -> str:
    where = "X @%s" % cfg.handle if post.source == "x" else "Codex changelog"
    when = post.created_at or "unknown time"
    limit = LONG_PREVIEW if long else SHORT_PREVIEW
    return (
        f"Possible Codex limits signal (score {score_total}: {score_hits})\n"
        f"Source: {where} | {when}\n"
        f"{post.url}\n"
        f"---\n"
        f"{_clip(post.body, limit)}"
    )


def format_title(post: Post) -> str:
    return f"Codex limits watch: {_clip(post.title, 80)}"


def _send_ntfy(cfg: Config, title: str, body: str, url: str) -> tuple[bool, str]:
    endpoint = f"{cfg.ntfy_server.rstrip('/')}/{cfg.ntfy_topic}"
    headers = {
        "Title": title.encode("utf-8"),
        "Priority": "high",
        "Tags": "arrow_counter_clockwise",
        "Click": url.encode("utf-8"),
    }
    status, response = http_post(endpoint, body.encode("utf-8"), headers=headers)
    return status == 200, f"ntfy [{status}] {_clip(response, 120)}"


def _send_telegram(cfg: Config, title: str, body: str, url: str) -> tuple[bool, str]:
    endpoint = f"https://api.telegram.org/bot{cfg.telegram_token}/sendMessage"
    payload = json.dumps({
        "chat_id": cfg.telegram_chat_id,
        "text": f"*{title}*\n\n{body}",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    status, response = http_post(endpoint, payload,
                                 headers={"Content-Type": "application/json"})
    ok = status == 200 and '"ok":true' in response.replace(" ", "")
    return ok, f"telegram [{status}] {_clip(response, 120)}"


def _send_email(cfg: Config, title: str, body: str) -> tuple[bool, str]:
    message = EmailMessage()
    message["Subject"] = title
    message["From"] = cfg.mail_from or cfg.smtp_user
    message["To"] = cfg.mail_to
    message.set_content(body)
    try:
        if cfg.smtp_port == 465:
            server = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=25,
                                      context=ssl.create_default_context())
            with server:
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(message)
        else:
            server = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=25)
            with server:
                server.starttls(context=ssl.create_default_context())
                server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(message)
        return True, "email sent"
    except (smtplib.SMTPException, OSError) as error:
        return False, f"email failed: {error}"


def send_alert(cfg: Config, post: Post, score_total: int, score_hits: str) -> list[tuple[bool, str]]:
    title = format_title(post)
    short = format_alert(cfg, post, score_total, score_hits)
    long_form = format_alert(cfg, post, score_total, score_hits, long=True)
    logs = []
    if cfg.ntfy_topic:
        logs.append(_send_ntfy(cfg, title, short, post.url))
    if cfg.telegram_token and cfg.telegram_chat_id:
        logs.append(_send_telegram(cfg, title, long_form, post.url))
    if cfg.smtp_host and cfg.mail_to:
        logs.append(_send_email(cfg, title, long_form))
    return logs


def send_test(cfg: Config) -> list[tuple[bool, str]]:
    title = "tibo-watcher test ping"
    body = ("If you can read this on your phone, the notification pipeline "
            "works. Real alerts will look similar.")
    logs = []
    if cfg.ntfy_topic:
        logs.append(_send_ntfy(cfg, title, body, "https://x.com/" + cfg.handle))
    if cfg.telegram_token and cfg.telegram_chat_id:
        logs.append(_send_telegram(cfg, title, body, "https://x.com/" + cfg.handle))
    if cfg.smtp_host and cfg.mail_to:
        logs.append(_send_email(cfg, title, body))
    return logs
