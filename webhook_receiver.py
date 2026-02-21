#!/usr/bin/env python3
"""Webhook receiver for auth-service outbound email events.

Listens for POST requests containing JSON payloads and optionally verifies
HMAC signatures produced by auth-service. On successful validation, forwards
an email via SMTP (for iRedMail or any SMTP relay).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import smtplib
from email.message import EmailMessage
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    host = os.getenv("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.getenv("WEBHOOK_PORT", "2555"))
    path = os.getenv("WEBHOOK_PATH", "/")

    webhook_secret = os.getenv("OUTBOUND_EMAIL_WEBHOOK_SECRET")
    require_signature = _env_bool("REQUIRE_SIGNATURE", default=False)

    smtp_host = os.getenv("SMTP_HOST", "mail.pentastarstudios.com")
    smtp_port = int(os.getenv("SMTP_PORT", "25"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_use_starttls = _env_bool("SMTP_USE_STARTTLS", default=False)
    smtp_from = os.getenv("SMTP_FROM", "no-reply@pentastarstudios.com")


def _json_response(handler: BaseHTTPRequestHandler, status: HTTPStatus, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _validate_signature(secret: str, timestamp: str, raw_body: bytes, provided_signature: str) -> bool:
    signed = timestamp.encode("utf-8") + b"." + raw_body
    digest = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, provided_signature)


def _build_text_body(payload: dict[str, Any]) -> str:
    event_type = payload.get("type", "unknown")
    token = payload.get("token", "")
    expires_at = payload.get("expiresAt", "")
    link = payload.get("link")

    lines = [
        "This email was generated from auth-service webhook event.",
        "",
        f"Type: {event_type}",
        f"Token: {token}",
        f"Expires At: {expires_at}",
    ]

    if link:
        lines.append(f"Link: {link}")

    lines.extend([
        "",
        "If you did not request this, you can ignore this message.",
    ])

    return "\n".join(lines)


def _send_email(payload: dict[str, Any]) -> None:
    to_addr = payload["to"]
    subject = payload["subject"]

    msg = EmailMessage()
    msg["From"] = Config.smtp_from
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(_build_text_body(payload))

    with smtplib.SMTP(Config.smtp_host, Config.smtp_port, timeout=30) as smtp:
        if Config.smtp_use_starttls:
            smtp.starttls()
        if Config.smtp_username and Config.smtp_password:
            smtp.login(Config.smtp_username, Config.smtp_password)
        smtp.send_message(msg)


class WebhookHandler(BaseHTTPRequestHandler):
    server_version = "AuthWebhookReceiver/1.0"

    def do_POST(self) -> None:  # noqa: N802 (HTTP verb method)
        if self.path != Config.path:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return

        content_length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(content_length)

        if Config.webhook_secret:
            timestamp = self.headers.get("X-TransLife-Timestamp", "")
            signature = self.headers.get("X-TransLife-Signature", "")
            if not timestamp or not signature:
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "missing_signature_headers"})
                return
            if not _validate_signature(Config.webhook_secret, timestamp, raw_body, signature):
                _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "invalid_signature"})
                return
        elif Config.require_signature:
            _json_response(self, HTTPStatus.UNAUTHORIZED, {"error": "signature_required"})
            return

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_json"})
            return

        required_fields = {"type", "to", "subject", "token", "expiresAt"}
        missing = [field for field in required_fields if field not in payload]
        if missing:
            _json_response(
                self,
                HTTPStatus.BAD_REQUEST,
                {"error": "missing_fields", "fields": missing},
            )
            return

        if payload["type"] not in {"email_verification", "password_reset"}:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "unsupported_type"})
            return

        try:
            dt.datetime.fromisoformat(str(payload["expiresAt"]).replace("Z", "+00:00"))
        except ValueError:
            _json_response(self, HTTPStatus.BAD_REQUEST, {"error": "invalid_expiresAt"})
            return

        try:
            _send_email(payload)
        except Exception as exc:  # noqa: BLE001
            logging.exception("Failed to send email")
            _json_response(
                self,
                HTTPStatus.BAD_GATEWAY,
                {"error": "smtp_delivery_failed", "details": str(exc)},
            )
            return

        _json_response(self, HTTPStatus.OK, {"status": "ok"})

    def do_GET(self) -> None:  # noqa: N802 (HTTP verb method)
        if self.path != Config.path:
            _json_response(self, HTTPStatus.NOT_FOUND, {"error": "not_found"})
            return
        _json_response(self, HTTPStatus.OK, {"status": "healthy"})

    def log_message(self, fmt: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = ThreadingHTTPServer((Config.host, Config.port), WebhookHandler)
    logging.info(
        "Webhook receiver listening on %s:%s path=%s smtp=%s:%s",
        Config.host,
        Config.port,
        Config.path,
        Config.smtp_host,
        Config.smtp_port,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down...")


if __name__ == "__main__":
    main()
