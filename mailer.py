#!/usr/bin/env python3
"""Standalone SMTP Mailer compatible with the user's established interface."""
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable, Optional

class Mailer:
    def __init__(self, enabled=False, smtp_host='localhost', smtp_port=25,
                 sender='oracle-refresh@localhost', recipients=None,
                 username=None, password=None, use_tls=False):
        self.enabled = str(enabled).lower() in ('1', 'true', 'yes', 'on') if isinstance(enabled, str) else bool(enabled)
        self.smtp_host = smtp_host
        self.smtp_port = int(smtp_port)
        self.sender = sender
        self.recipients = self._split_recipients(recipients)
        self.username = username or None
        self.password = password or None
        self.use_tls = str(use_tls).lower() in ('1', 'true', 'yes', 'on') if isinstance(use_tls, str) else bool(use_tls)

    @staticmethod
    def _split_recipients(recipients):
        if not recipients: return []
        if isinstance(recipients, str):
            return [x.strip() for x in recipients.split(',') if x.strip()]
        return list(recipients)

    def send(self, subject: str, body: str, attachments: Optional[Iterable[str]] = None) -> bool:
        if not self.enabled or not self.recipients:
            return False
        msg = EmailMessage()
        msg['From'] = self.sender
        msg['To'] = ', '.join(self.recipients)
        msg['Subject'] = subject
        msg.set_content(body)
        for item in attachments or []:
            path = Path(item)
            if path.is_file() and path.stat().st_size <= 256 * 1024:
                msg.add_attachment(path.read_bytes(), maintype='application',
                                   subtype='octet-stream', filename=path.name)
        if self.username and (not self.use_tls or not self.password):
            raise RuntimeError('Authenticated SMTP requires STARTTLS and password')
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if self.use_tls:
                if not smtp.has_extn('starttls'):
                    raise RuntimeError('SMTP does not advertise STARTTLS')
                smtp.starttls(context=ssl.create_default_context())
                smtp.ehlo()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(msg)
        return True
