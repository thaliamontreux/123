# auth-service webhook receiver for iRedMail

This service receives auth-service outbound email webhooks and relays them to SMTP.

## What it expects from auth-service

`POST` JSON to your receiver (default `/` on port `2555`):

- `type`: `email_verification` or `password_reset`
- `to`: destination email address
- `subject`: email subject
- `token`: raw one-time token
- `expiresAt`: ISO timestamp
- `link`: optional (included by auth-service when `PUBLIC_WEB_URL` is set)

If `OUTBOUND_EMAIL_WEBHOOK_SECRET` is configured, auth-service includes:

- `X-TransLife-Timestamp`
- `X-TransLife-Signature`: `hex(hmac_sha256(secret, timestamp + "." + rawBody))`

This receiver validates those headers when secret is set.

## Run

```bash
python3 webhook_receiver.py
```

Defaults:

- bind: `0.0.0.0:2555`
- path: `/`
- smtp host: `mail.pentastarstudios.com`
- smtp port: `25`

## Environment variables

- `WEBHOOK_HOST` (default `0.0.0.0`)
- `WEBHOOK_PORT` (default `2555`)
- `WEBHOOK_PATH` (default `/`)
- `OUTBOUND_EMAIL_WEBHOOK_SECRET` (optional; validates signed webhook requests)
- `REQUIRE_SIGNATURE` (default `false`; set true to reject unsigned requests when no secret is set)
- `SMTP_HOST` (default `mail.pentastarstudios.com`)
- `SMTP_PORT` (default `25`)
- `SMTP_USERNAME` (optional)
- `SMTP_PASSWORD` (optional)
- `SMTP_USE_STARTTLS` (`true/false`, default `false`)
- `SMTP_FROM` (default `no-reply@pentastarstudios.com`)

## Example systemd service

```ini
[Unit]
Description=Auth Webhook Receiver
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/auth-webhook
ExecStart=/usr/bin/python3 /opt/auth-webhook/webhook_receiver.py
Environment=WEBHOOK_PORT=2555
Environment=WEBHOOK_PATH=/
Environment=SMTP_HOST=mail.pentastarstudios.com
Environment=SMTP_PORT=25
# Environment=OUTBOUND_EMAIL_WEBHOOK_SECRET=replace_me
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Quick test with signature

```bash
body='{"type":"email_verification","to":"user@example.com","subject":"Verify your email","token":"abc123","expiresAt":"2026-01-01T00:00:00Z","link":"https://app.example.com/verify"}'
ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
secret='replace_me'
sig="$(printf '%s.%s' "$ts" "$body" | openssl dgst -sha256 -hmac "$secret" -hex | sed 's/^.* //')"
curl -i -X POST http://127.0.0.1:2555/ \
  -H 'Content-Type: application/json' \
  -H "X-TransLife-Timestamp: $ts" \
  -H "X-TransLife-Signature: $sig" \
  --data "$body"
```
