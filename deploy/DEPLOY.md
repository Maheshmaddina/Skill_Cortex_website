# Deploying Skill Cortex to a VPS

One server runs everything with Docker Compose:

```
Internet ──443──> caddy (HTTPS, Let's Encrypt)
                   ├── /api/*  → backend  (FastAPI, uvicorn workers) ─┐
                   └── /*      → frontend (nginx, built React app)     ├─> db (PostgreSQL, not exposed)
                                 scheduler (one instance) ─────────────┘
                                 migrate (runs migrations + seed on each deploy, then exits)
```

## 1. Server

- Ubuntu 24.04 LTS, 2 vCPU / 4 GB RAM is plenty to start.
- Install Docker Engine and the Compose plugin: https://docs.docker.com/engine/install/ubuntu/
- Firewall — only SSH and web traffic:
  ```bash
  sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw allow 443/udp && sudo ufw enable
  ```
- Point DNS at the server: an `A` record (and `AAAA` if you have IPv6) for your domain. Caddy obtains the certificate automatically once DNS resolves and ports 80/443 are reachable.

## 2. First deploy

```bash
sudo mkdir -p /opt/skill-cortex && sudo chown "$USER" /opt/skill-cortex
git clone <your-repo-url> /opt/skill-cortex && cd /opt/skill-cortex

cp .env.production.example .env.production
chmod 600 .env.production
# Fill it in. Generate secrets with:  openssl rand -hex 24   (POSTGRES_PASSWORD)
#                                     openssl rand -hex 48   (JWT_SECRET)

docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker compose --env-file .env.production -f docker-compose.prod.yml ps     # all Up; migrate "Exited (0)"
curl https://<DOMAIN>/api/health                                           # {"status":"ok","database":"ok"}
```

The API refuses to start with an unsafe configuration (weak `JWT_SECRET`, `COOKIE_SECURE` not true, non-https `FRONTEND_URL`, `CORS_ORIGINS=*`, rate limiting off) — check `docker compose ... logs backend` if it restarts.

Create the first admin (no public admin signup):

```bash
docker compose --env-file .env.production -f docker-compose.prod.yml exec -e ADMIN_PASSWORD='<strong password>' backend \
  python -m app.scripts.create_admin --email you@example.com --name "Your Name" --phone 9876543210
```

Then log in at `https://<DOMAIN>/login` → you land on `/admin`.

## 3. Integrations

**Razorpay** (Dashboard → Settings)
- API keys → `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`. Test keys (`rzp_test_…`) first; switch to live keys after a full test booking.
- Webhooks → URL `https://<DOMAIN>/api/payments/webhook`, events `payment.captured`, `payment.failed` (optionally `order.paid`), and a secret → `RAZORPAY_WEBHOOK_SECRET`.
- Keep automatic payment capture enabled.

**Email** — any SMTP / transactional provider (Amazon SES, Brevo, Postmark…): `EMAIL_PROVIDER=smtp` and `SMTP_*`. Set up SPF/DKIM for the `EMAIL_FROM` domain so confirmations don't land in spam.

**SMS** — MSG91 with DLT-registered templates, one per message type (`MSG91_TEMPLATE_*`). Template variables: `name, webinar, date, time, amount, booking_id, payment_ref` (reminders also get `when`). Use `SMS_PROVIDER=console` to run without SMS.

After changing `.env.production`: `docker compose --env-file .env.production -f docker-compose.prod.yml up -d` (recreates the containers that use it).

## 4. Updating

```bash
cd /opt/skill-cortex
./deploy/backup.sh                                     # always back up before an update
git pull
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
docker image prune -f
```

`migrate` runs again automatically before the backend and scheduler start. If a migration fails, the app containers don't start and the previous database state is untouched (migrations run in a transaction) — fix and redeploy, or roll back with `git checkout <previous tag>` and redeploy.

## 5. Backups

```bash
./deploy/backup.sh                                     # → backups/skill_cortex_<UTC timestamp>.sql.gz, keeps 14 days
crontab -e   # add:  30 2 * * * cd /opt/skill-cortex && ./deploy/backup.sh >> backups/backup.log 2>&1
./deploy/restore.sh backups/skill_cortex_<timestamp>.sql.gz   # asks for confirmation
```

Copy backups off the server too (e.g. `rclone` to object storage) — a backup on the same disk doesn't survive losing the VPS.

## 6. Operations

| Task | Command (prefix: `docker compose --env-file .env.production -f docker-compose.prod.yml`) |
|---|---|
| Status | `ps` |
| Logs | `logs -f backend` · `logs -f scheduler` · `logs -f caddy` |
| Restart app | `restart backend scheduler` |
| DB shell | `exec db sh -c 'psql -U "$POSTGRES_USER" "$POSTGRES_DB"'` |
| Stop everything | `down` (data volumes are kept; never add `-v` unless you mean to delete all data) |

Monitoring: point an uptime checker at `https://<DOMAIN>/api/health`, and watch the admin dashboard's failed-payment and failed-notification counts.

## Notes

- Run exactly **one** `scheduler` container; scale the API with `WEB_CONCURRENCY` instead.
- Per-IP rate limits rely on `X-Forwarded-For` from Caddy. If you put a CDN/proxy (e.g. Cloudflare) in front, configure Caddy's `trusted_proxies` so the real client IP is used.
- The frontend's Content-Security-Policy (`frontend/nginx/security-headers.conf`) allows Razorpay Checkout; add any new third-party script or frame origins there.
