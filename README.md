# Skill Cortex V1

Webinar / course booking platform: department → webinar → slot → Razorpay payment → verified confirmation → email/SMS → automated reminders.

Specs live in the PDFs at the repo root. Stack: FastAPI + PostgreSQL + SQLAlchemy/Alembic (backend), React + Tailwind (frontend, later phase).

## Quick start (Docker)

```bash
docker compose up -d --build                          # Postgres 16 + API on :8000
docker compose exec backend alembic upgrade head      # create schema
docker compose exec backend python -m app.scripts.seed  # departments + reminder rules
docker compose exec backend python -m app.scripts.seed_catalog  # optional: starter courses at ₹999, 18 sessions each (re-run to top up)
curl localhost:8000/health                            # {"status":"ok","database":"ok"}
docker compose exec backend pytest -q                 # run tests (uses skill_cortex_test DB)
```

API docs: http://localhost:8000/docs

Create an admin (there is no public admin signup):

```bash
docker compose exec -e ADMIN_PASSWORD='Str0ngPass' backend \
  python -m app.scripts.create_admin --email admin@example.com --name "Skill Cortex Admin" --phone 9876543210
```

## Vercel deployment

Live at **https://skill-cortex-website.vercel.app** (Vercel project `skill-cortex-website`, database Neon via the Vercel Marketplace).
- `vercel.json` builds the React app (`frontend/dist`) and serves the FastAPI app as the Python function `api/index.py` under `/api` (`backend/app/serverless.py` mounts it). Root `requirements.txt` must match `backend/requirements.txt` (a test checks).
- There is no long-running scheduler on Vercel: `GET /api/internal/run-jobs` (header `Authorization: Bearer $CRON_SECRET`) runs every job once. Vercel Cron calls it daily; `.github/workflows/run-jobs.yml` calls it every 5 minutes once the repository secrets `APP_URL` and `CRON_SECRET` are set.
- Production env vars (Vercel → Settings → Environment Variables): `APP_ENV=production`, `DATABASE_URL` (from Neon), `DATABASE_POOL=null`, `JWT_SECRET`, `COOKIE_SECURE=true`, `REFRESH_COOKIE_PATH=/api/auth`, `FRONTEND_URL` and `CORS_ORIGINS` (the site URL), `CLIENT_IP_HEADER=x-real-ip`, `CRON_SECRET`; add Razorpay / SMTP / MSG91 values to enable payments and real email/SMS.
- Migrations and seeding run from a machine with the Neon URL: `DATABASE_URL=<unpooled Neon URL> alembic upgrade head`, then `python -m app.scripts.seed`, `seed_catalog`, `create_admin`.
- Deploy: `vercel deploy --prod` (or push to `main` once the GitHub repo is connected to the Vercel project).

## Production deployment

Everything runs on one VPS with Docker Compose: Caddy (automatic HTTPS) → React app (nginx) and API under `/api` (FastAPI), plus the scheduler and PostgreSQL. Full runbook: **[deploy/DEPLOY.md](deploy/DEPLOY.md)**.

```bash
cp .env.production.example .env.production   # fill in domain, secrets, Razorpay, SMTP, MSG91
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
./deploy/backup.sh                           # nightly via cron; restore with deploy/restore.sh
```

CI (`.github/workflows/ci.yml`) runs backend tests against PostgreSQL with a migration drift check, frontend tests and build, dependency audits, and builds both production images.

## Frontend

React 19 + Tailwind 4 (Vite) in `frontend/`. `docker compose up -d` starts it at **http://localhost:5173** (API at :8000).

```bash
cd frontend && npm install && npm run dev   # or run it on the host instead of in Docker
npm test                                    # Vitest unit/component tests
npm run build                               # production build → frontend/dist
```

Config (`frontend/.env`): `VITE_API_URL` (default `http://localhost:8000`), `VITE_CONTACT_EMAIL`.

- **Learner portal:** landing page, catalog (filtered to the learner's department by default), webinar details with slot picker, booking review with a live seat-hold countdown, Razorpay Checkout → server verification → confirmation, My Bookings (upcoming/previous), notifications, profile.
- **Admin portal (`/admin`):** dashboard, departments, webinars (+ per-webinar slots: add, edit, deactivate, cancel session with refunds), bookings (cancel/refund), payments, users (activate/deactivate), notifications (retry), reminder schedule.
- Auth: the access token is kept in memory only; the httpOnly refresh cookie restores the session on reload and renews expired tokens automatically. All dates/times display in IST.

## Auth

- `POST /auth/register` → learner account (department required) · `POST /auth/login` → access token (60 min) in the body + refresh token in an httpOnly cookie scoped to `/auth`
- `POST /auth/refresh` rotates the refresh token (replaying an old one revokes all sessions) · `POST /auth/logout`
- `POST /auth/forgot-password` (same response whether or not the email exists; in development the reset link is logged) · `POST /auth/reset-password`
- `GET/PUT /users/me` · `GET /departments` (public)
- Send `Authorization: Bearer <access_token>`; admin routes use the `AdminUser` dependency, which checks the role stored in the database.

## Catalog

Public (no login): `GET /webinars?department_id=&q=&page=&page_size=` (cards with next open slot + seats left, soonest first) · `GET /webinars/{id}` · `GET /webinars/{id}/slots` (upcoming active slots; full ones flagged `is_full`).

Admin (all under `/admin`, admin role required):
- `departments` — list/create/get/update; `DELETE` deactivates
- `webinars` — list (filters `status`, `department_id`, `q`)/create/get/update; `DELETE` deactivates (existing bookings stay valid)
- `slots` — list (`webinar_id`, `upcoming`)/create/get/update; `DELETE` deactivates. Times must be timezone-aware and in the future. Capacity can't go below booked seats; rescheduling or deactivating a slot with pending/confirmed bookings returns 409.

Money is in paise (`price_paise: 99900` = ₹999). Errors are `{"detail": "..."}` with a user-facing message.

## Learner-set webinars ("Set webinar")

Learners aren't limited to published sessions: they pick a course plus any date and start time (IST, half-hour steps 7:00 AM–9:00 PM, tomorrow to 90 days out) and press **Set webinar** — the team conducts it then.
- `POST /bookings/set-webinar {webinar_id, preferred_date, preferred_time, note}` creates the session at that time (60 seats, `slots.set_by_user_id` = the learner) or joins any active session already at that exact time, and holds the learner's seat as a normal `PENDING` booking → pay → `CONFIRMED`, reminders, admin payment alert (which notes the learner chose the time). Repeating it returns the same unpaid booking (200).
- `GET /webinars?preferred_date=&preferred_time=` adds `matching_slot` to each card when a session already runs then.
- Admin: `GET /admin/slots?learner_set=true` (UI: **Learner webinars**) lists them with who set them and their notes; the dashboard counts upcoming learner-set sessions.
- The scheduler withdraws (deactivates) learner-set sessions that have had no pending/confirmed booking for an hour, so abandoned choices don't linger.

## Bookings

Learner (login required, learner accounts only):
- `POST /bookings {"slot_id"}` → holds one seat for 15 minutes as a `PENDING` booking while the learner pays (price is snapshotted). Repeating the call for the same slot returns the existing hold (200) instead of taking another seat. Free webinars (`price_paise: 0`) are `CONFIRMED` immediately. Full slot → 409 "This slot is full…".
- `GET /bookings?scope=upcoming|past` · `GET /bookings/{id}` · `POST /bookings/{id}/cancel` (unpaid bookings only; releases the seat)

Admin: `GET /admin/bookings?status=&webinar_id=&slot_id=&user_id=&q=` (q = reference, learner name or email) · `GET /admin/bookings/{id}`

Seats are taken with a single conditional `UPDATE` on the slot row, so concurrent requests can't oversell (see `tests/test_booking_concurrency.py`).

## Payments (Razorpay)

Put **test-mode** keys in a project-root `.env` (docker compose passes them to the containers), then `docker compose up -d`:

```
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...   # the secret you set on the webhook in the Razorpay dashboard
```

Flow (frontend):
1. `POST /bookings` → `PENDING` booking (seat held 15 min)
2. `POST /payments/create-order {"booking_id"}` → `key_id`, `order_id`, `amount_paise`, `prefill` → open Razorpay Checkout with them (calling it again reuses the open order)
3. Checkout `handler` → `POST /payments/verify {razorpay_order_id, razorpay_payment_id, razorpay_signature}` → `{outcome, message, booking}`; the booking is `CONFIRMED` only after the server checks the signature

Webhook: point Razorpay at `POST https://<api-host>/payments/webhook` with events `payment.captured`, `payment.failed` (and optionally `order.paid`). It confirms bookings even if the learner closes the browser before step 3, ignores replays (by `X-Razorpay-Event-Id`) and rejects bad signatures. Keep automatic capture enabled in the Razorpay dashboard. For local testing expose port 8000 with a tunnel (e.g. `ngrok http 8000`).

Rules:
- Verify and webhook share one idempotent `confirm_payment` (row-locked), so a booking is confirmed once whichever arrives first; webhook amounts must match the order.
- A payment that completes after its hold expired re-takes a seat if one is free, otherwise it is refunded in full and the booking marked `FAILED`.
- A failed attempt marks that order `FAILED`; the learner can retry (a new order) while the hold lasts.

Admin: `GET /admin/payments?status=&booking_id=&q=` · `GET /admin/payments/{id}` · `POST /admin/bookings/{id}/cancel` (refunds a paid booking, releases the seat) · `POST /admin/slots/{id}/cancel` (cancels the session, cancels every live booking and refunds paid ones; safe to re-run if a refund fails).

## Notifications (email / SMS)

Every message is first stored as a `PENDING` row in `notifications`, in the same transaction as the event that caused it — so a confirmed payment can never lose its confirmation. Delivery happens right after the API response, and the scheduler retries anything left over every minute. A failed delivery is retried after 5, then 10 minutes and marked `FAILED` after `NOTIFICATION_MAX_ATTEMPTS` (3); the booking is never affected.

| Event | Learner | Admin (`ADMIN_NOTIFY_EMAILS` / `ADMIN_NOTIFY_PHONES`) |
|---|---|---|
| Registration | welcome email | — |
| Payment verified (Checkout or webhook) / free booking | confirmation email + SMS (webinar, date, time IST, amount, booking ID, payment ref) | payment email + SMS (paid bookings only) |
| Admin cancels booking or slot | cancellation email + SMS, with refund details | — |
| Payment arrived after the slot filled | refund email + SMS | — |
| Forgot password | reset email (sent once; the link is never stored) | — |

Providers (root `.env`): `EMAIL_PROVIDER=console|smtp` (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_USE_TLS`, `EMAIL_FROM`) and `SMS_PROVIDER=console|msg91` (`MSG91_AUTH_KEY` + one DLT-approved template id per type: `MSG91_TEMPLATE_BOOKING_CONFIRMATION`, `_ADMIN_PAYMENT`, `_CANCELLATION`, `_REFUND`, `_REMINDER`; template variables: `name, webinar, date, time, amount, booking_id, payment_ref`). With `console`, messages appear in `docker compose logs backend`.

API: `GET /notifications` (learner's own) · `GET /admin/notifications?status=&type=&channel=&booking_id=&user_id=&q=` · `GET /admin/notifications/{id}` · `POST /admin/notifications/{id}/retry`.

## Admin dashboard & users

- `GET /admin/dashboard/stats` — learners (total, new in 30 days), admins, webinars (total/active), upcoming sessions, bookings by status, payments (successful/pending/failed/refunded), revenue in paise (total and last 30 days; `PAID` payments only, refunds excluded), pending/failed notifications, and the next 5 sessions with booked vs available seats.
- `GET /admin/users?q=&department_id=&role=&is_active=` — newest first, each with `bookings_count`, `confirmed_bookings_count` and `total_paid_paise` (q matches name, email or phone) · `GET /admin/users/{id}`
- `PUT /admin/users/{id} {"is_active": false}` — deactivate (signs the user out everywhere; bookings are kept) or reactivate; admins can't deactivate themselves.
- A user's bookings and payments: `GET /admin/bookings?user_id=` · `GET /admin/payments?user_id=`

## Reminders

Confirmed bookings get automatic reminders by email + SMS. The default schedule (seeded by `app.scripts.seed`):

| Rule | Sent at (IST) | Message |
|---|---|---|
| 3 days before | 09:00 | "Your Python webinar is in 3 days (Sun, 20 Sep 2026, 10:00 AM IST)." |
| 2 days before | 09:00 | "… is in 2 days …" |
| 1 day before | 09:00 | "Your Python webinar is tomorrow at 10:00 AM IST." |
| Same day | 08:00, or 2 hours before the start if earlier | "Your Python webinar starts today at 10:00 AM IST." |

- Only `CONFIRMED` bookings for active, not-yet-started slots get reminders; one queued before a cancellation is dropped at send time.
- Each reminder is sent at most once (unique index on booking + channel + recipient + offset).
- Per run, a booking gets only the most recent due reminder — someone who books the day before gets the 1-day and same-day reminders, not a late "in 3 days". Reminders that came due before the booking was confirmed are skipped.

Admin: `GET /admin/reminder-rules` · `POST /admin/reminder-rules {"offset_days": 7, "send_time_local": "18:30", "send_email": true, "send_sms": false}` · `PUT /admin/reminder-rules/{id}` (e.g. `{"active": false}` to pause) · `DELETE /admin/reminder-rules/{id}`.

## Security

- **Rate limits** (429 + `Retry-After`), counted in Postgres so they hold across API workers; failed attempts count too. Per account: login 10 / 15 min, forgot-password 3 / hour. Per IP (generous, for shared campus networks): login 100 / 15 min, register 50 / hour, forgot-password 30 / hour, reset-password 20 / 15 min, refresh 300 / 5 min. Per learner: bookings and payment calls 30 / 10 min. Set `RATE_LIMIT_ENABLED=false` only for local testing. Behind a reverse proxy, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy>` so limits see real client IPs.
- **Headers** on every API response: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, a deny-all `Content-Security-Policy`, and HSTS when `COOKIE_SECURE=true`.
- Request bodies over `MAX_REQUEST_BODY_BYTES` (1 MB) get 413; unexpected errors return a generic 500 message (details only in server logs).
- **Production guard:** with `APP_ENV=production` the API refuses to start unless `JWT_SECRET` is strong, `COOKIE_SECURE=true`, `CORS_ORIGINS` is explicit (no `*`) and rate limiting is on; `/docs` and `/openapi.json` are disabled.
- Sessions: refresh tokens rotate on every use; replaying an old token ends all of that user's sessions (two tabs refreshing within 30 seconds are treated as a harmless race, not theft).
- `tests/test_security.py` fails if any route other than the explicit public list is reachable without login, or any `/admin` route is reachable by a learner.
- Dependency audit (last run 2026-09-14: no known vulnerabilities): `docker compose exec backend sh -c "pip install -q pip-audit && pip-audit -r requirements.txt"` and `cd frontend && npm audit`.

## Scheduler

The `scheduler` compose service (`python -m app.scheduler`) runs background jobs — run exactly one instance:
- every minute: expire unpaid holds past their deadline, release their seats, fail their pending payments
- every minute: deliver pending notifications and retry failed ones
- every 5 minutes: queue due reminders
- every 10 minutes: mark confirmed bookings whose session has ended as `COMPLETED`
- every hour: delete expired rate-limit counters

Logs: `docker compose logs -f scheduler`

## Layout

```
backend/
  app/
    main.py, config.py, database.py
    models/      SQLAlchemy models (users, departments, webinars, slots, bookings, payments, notifications, ...)
    schemas/ routes/ services/ utils/ scheduler/   (filled in by later phases)
    scripts/seed.py
  alembic/       migrations
  tests/
docker-compose.yml
```

## Build phases

1. ER design ✅ · 2. FastAPI + PostgreSQL setup ✅ · 3. Auth & roles ✅ · 4. Departments/webinars/slots ✅ · 5. Booking & seat hold ✅ · 6. Razorpay ✅ · 7. Email/SMS ✅ · 8. Reminder scheduler ✅ · 9. Admin dashboard ✅ · 10. Frontend ✅ · 11. Testing & security ✅ · 12. Docker + VPS deploy ✅
