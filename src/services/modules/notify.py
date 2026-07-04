import os
import re
import smtplib
import ssl
from email.message import EmailMessage

import requests

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")


class NotifyService:
    def __init__(self) -> None:
        self.smtp_host = os.environ.get("SMTP_HOST")
        self.smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        self.smtp_user = os.environ.get("SMTP_USER")
        self.smtp_password = os.environ.get("SMTP_PASSWORD")
        self.from_email = os.environ.get("FROM_EMAIL", self.smtp_user or "")

        self.twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        self.twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
        self.twilio_from = os.environ.get("TWILIO_FROM_NUMBER")

    def classify(self, contact: str) -> str:
        cleaned = contact.strip()
        if EMAIL_RE.match(cleaned):
            return "email"
        if PHONE_RE.match(cleaned.replace(" ", "").replace("-", "")):
            return "phone"
        return "unknown"

    def send_share_details(self, contact: str, filename: str, portal_url: str, pin: str) -> None:
        contact = contact.strip()
        kind = self.classify(contact)
        body = (
            f"A file was shared with you via ScanOnce.\n\n"
            f"File: {filename}\n"
            f"Link: {portal_url}\n"
            f"PIN: {pin}\n\n"
            f"This link works once and expires automatically within 1 hour."
        )
        if kind == "email":
            self._send_email(contact, filename, body)
        elif kind == "phone":
            self._send_sms(contact, body)
        else:
            raise ValueError(f"'{contact}' doesn't look like a valid email address or phone number")

    def _send_email(self, to_email: str, filename: str, body: str) -> None:
        if not (self.smtp_host and self.smtp_user and self.smtp_password):
            raise RuntimeError(
                "Email delivery isn't configured yet "
                "(missing SMTP_HOST / SMTP_USER / SMTP_PASSWORD env vars)"
            )
        msg = EmailMessage()
        msg["Subject"] = f"File shared with you: {filename}"
        msg["From"] = self.from_email
        msg["To"] = to_email
        msg.set_content(body)

        context = ssl.create_default_context()
        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
            server.starttls(context=context)
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

    def _send_sms(self, to_number: str, body: str) -> None:
        if not (self.twilio_sid and self.twilio_token and self.twilio_from):
            raise RuntimeError(
                "SMS delivery isn't configured yet "
                "(missing TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER env vars)"
            )
        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        response = requests.post(
            url,
            data={"From": self.twilio_from, "To": to_number, "Body": body},
            auth=(self.twilio_sid, self.twilio_token),
            timeout=10,
        )
        response.raise_for_status()


notify_service = NotifyService()
