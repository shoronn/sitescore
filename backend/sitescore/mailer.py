"""Outgoing email. Without SMTP settings, emails are printed to the log (development)."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from email.message import EmailMessage

import aiosmtplib

from .config import Settings

log = logging.getLogger("sitescore.mail")

@dataclass
class Attachment:
    filename: str
    content: bytes
    mime: str = "application/pdf"


@dataclass
class Outgoing:
    to: str
    subject: str
    text: str
    html: str
    attachments: list[Attachment] = field(default_factory=list)


# Messages "sent" without SMTP are kept here so tests and local runs can read them.
OUTBOX: list[Outgoing] = []


async def send(settings: Settings, msg: Outgoing) -> None:
    if not settings.smtp_host:
        OUTBOX.append(msg)
        del OUTBOX[:-50]
        log.warning("SMTP not configured; email to %s: %s\n%s", msg.to, msg.subject, msg.text)
        return
    em = EmailMessage()
    em["From"] = settings.mail_from
    em["To"] = msg.to
    em["Subject"] = msg.subject
    em.set_content(msg.text)
    em.add_alternative(msg.html, subtype="html")
    for a in msg.attachments:
        maintype, subtype = a.mime.split("/", 1)
        em.add_attachment(a.content, maintype=maintype, subtype=subtype, filename=a.filename)
    await aiosmtplib.send(
        em, hostname=settings.smtp_host, port=settings.smtp_port,
        username=settings.smtp_user or None, password=settings.smtp_password or None,
        start_tls=settings.smtp_starttls if settings.smtp_port != 465 else False,
        use_tls=settings.smtp_port == 465, timeout=20,
    )

