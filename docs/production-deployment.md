# Production deployment notes

This app is deployed as plain HTTP behind a reverse proxy — it never
terminates TLS itself, and no code here claims otherwise.

## Reverse proxy / HTTPS

Put nginx, Caddy, or the platform's own load balancer in front of the
FastAPI process, terminating TLS there. The proxy is responsible for:

- TLS termination (a real certificate — Let's Encrypt via Caddy's
  automatic HTTPS, or your platform's managed certificate).
- Redirecting HTTP to HTTPS.
- Setting `Strict-Transport-Security` (HSTS) — only safe to set once
  HTTPS is actually working end-to-end, which is why it's a proxy-layer
  concern and not set by the app itself (`app/main.py`'s
  `_security_headers` middleware only sets headers that are correct
  regardless of the transport: `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`).
- Forwarding `X-Forwarded-For`/`X-Forwarded-Proto` so the app sees the
  real client IP and scheme if it ever needs them.

Example nginx snippet (adapt certificate paths and upstream port to the
actual deployment):

```nginx
server {
    listen 443 ssl;
    server_name your-domain.example;
    ssl_certificate     /etc/letsencrypt/live/your-domain.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.example/privkey.pem;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
    }
}
server {
    listen 80;
    server_name your-domain.example;
    return 301 https://$host$request_uri;
}
```

## Health check

`GET /health` checks real database connectivity (`SELECT 1`), not just
that the process is alive, and returns 503 if the database is
unreachable. Point the orchestrator's liveness/readiness probe at this
path.

## CORS

`CORS_ALLOWED_ORIGINS` (comma-separated) must be set explicitly in
production to the real frontend origin(s) — it defaults to
`http://localhost:3000` for local development only. Never set it to `*`
while `allow_credentials=True` is set (browsers reject that combination
anyway, and it would be unsafe even if they didn't).

## Secrets

`JWT_SECRET` and `BSN_ENCRYPTION_KEY` both ship with insecure placeholder
defaults that log a warning on startup if left unchanged (see
`app/core/config.py`). Both must be set to real, randomly generated
values before this is reachable from anywhere but a developer's own
machine. See `docs/encryption-key-rotation.md` for how to change
`BSN_ENCRYPTION_KEY` safely once real BSNs are stored.

## What is not covered here

- No Docker Compose file or Dockerfile has been authored as part of this
  phase — if containerizing, the app needs the standard `pip install -r
  requirements.txt` + `alembic upgrade head` + `uvicorn app.main:app`
  sequence, with `DATABASE_URL` pointed at a real Postgres instance.
- No managed logging/monitoring/error-reporting service is wired up (no
  Sentry, no centralized log shipping) — stdout/stderr logging only,
  suitable for capture by whatever the deployment platform already
  provides.
