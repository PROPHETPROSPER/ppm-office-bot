# PPM Office Bot — Owner-controlled internal deployment (v4, October 12, 2026)

**Mode: OFFICE ONLY.** Set `PPM_BOT_MODE=office` in Railway; the public subscriber bot will be a separate Telegram identity later. This internal mode blocks the public `/start` onboarding and `/alerts` subscription interface, and only Telegram IDs explicitly granted staff roles can interact with `/new`, `/queue`, `/preview`, `/approve`, and `/send`.

**Local test status:** 37 passed, including office-only access tests and identity verification. This is not a live deployment. Messages and scheduler disabled (`LIVE_SENDING_ENABLED=false`, `PPM_SCHEDULER_ENABLED=false`).

**Hosting:** Railway `PPM Private Test` → environment `private-test` → staged service `ppm-bot`. The BotFather token is staged as a private variable. The service still needs the SOURCE from this repository to be attached; do not approve Railway staging while its source is missing. Upload the files at the ROOT of a private GitHub repository, then attach that repository to the existing Railway service and verify it is using `Dockerfile` at repository root. The service start command is `python -m app.entrypoint` and health check is `/health`.

**Credential protection:** Never put your BotFather token, admin secret, webhook secret, or member details in the repository. The `.env.example` is a blank template; `.gitignore` excludes `.env`.

**Telegram identity check:** After deployment and adding `APP_ADMIN_TOKEN`, a restricted `GET /admin/telegram/identity` validates that the BotFather token belongs to **@PPMOfficeBot**. The bot must not register a webhook or send until this check returns `verified: true`.

**Remaining required private configuration:** `APP_ADMIN_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `TELEGRAM_OWNER_USER_IDS` (your numeric Telegram ID), and a private test chat ID. Set these as Railway secrets. Do not use public chat IDs during first live test.

----

# PPM Telegram Bot v3 — Owner-Controlled Deployment Package

**Purpose:** Run approved Prophet Prosper Ministries communications through Telegram without overloading Michelle or volunteers. **Status: offline-tested code, not deployed.** No messages or purchases have been sent by this package.

## What is implemented

- **Three destinations:** main official channel, free private mentorship group (~80), paid Spiritual Foundation group (~35). Group welcome posts only in authorized groups.
- **Member self-service:** `/start`, `/alerts` (six categories), `/events` (event-specific opt-in), `/status`, `/schedule`, `/stop`.
- **Easy staff interface:** `/new` → choose destination → choose topic → type announcement. Bot saves a draft, **not a post**. Advanced alternative: `/draft official|schools|Message`.
- **Separate roles:** editor drafts; approver approves/rejects; publisher sends approved material; owner has all privileges. Numeric Telegram user IDs, not account passwords. `/queue`, `/preview ID`, `/approve ID`, `/reject ID`, `/send ID`.
- **Scheduled events:** Wix read-only event import held for approval, a 14/10/7/5/3/2/1/day-of calendar with anti-spam limits, event-specific personal reminders for opted-in members, and revocation when an event's public details change.
- **Livestream checking:** authenticated YouTube active-broadcast checks, conservative title-and-time classification, one alert per verified stream and destination. Unknown/private streams are held. Owner may opt in to *template-policy* approval of recognized alerts after testing.
- **Recurring ministry reminders:** M/W/F 9 AM morning prayer; Oct 11–Nov 9 daily 6 PM Zoom prayer; Monday–Saturday evening teaching, no Sunday YouTube teaching; private Saturday 2 PM mentorship **except Oct 24 conflicting with Watchman Series**. Never invent Zoom links.
- **Safe dispatch:** all Telegram sending is behind `LIVE_SENDING_ENABLED` and approval checks. Personal deliveries are recorded individually, recipients throttle at ~20/second, retries of ambiguous partial sends require manual intervention, and Telegram updates are deduplicated so duplicate callback deliveries don't switch preferences twice.
- **AI content drafts:** existing transcript-based AI drafting and quote verification (not finished video editing or live Instagram publishing).
- **WhatsApp / Clearstream:** review/export only, no mass sending from this bot.
- **MoreThanPanel:** service-catalog/balance **read only**; **no ordering/purchasing endpoints**.
- **Confidential event safeguards:** no private Dallas promotions or relocation plans in ordinary bot messages.

## Railway deployment status (Oct 12, 2026)

The owner has an existing Railway project called `PPM Private Test`. Its bot service and database volume are **staged, not live**. Service configuration has been staged with an East US region to match the staged volume, a `/health` check, and `python -m app.entrypoint` as the start command. All outbound and scheduler settings are staged as disabled. The service **does not yet have a GitHub/Docker image source** attached. See `docs/OWNER_ACTIVATION_STEPS.md`.

The updated `Dockerfile` launches the web API and, only when `PPM_SCHEDULER_ENABLED=true`, the background scheduler in the same one-replica container. It uses `PORT` and defaults to a persistent SQLite file at `PPM_DATA_DIR/ppm.sqlite3` or `DB_PATH`. An authenticated `GET /admin/readiness` reports missing configuration names without exposing secret values.

## Start in a private test environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Configure long random APP_ADMIN_TOKEN and TELEGRAM_WEBHOOK_SECRET. Leave LIVE_SENDING_ENABLED=false.
python -m pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8080
# Open http://127.0.0.1:8080/docs and use bearer APP_ADMIN_TOKEN for protected API calls.
```

Docker alternative: `docker compose up --build -d`. Put a TLS-terminating reverse proxy in front; never publish database ports. Run only **one** scheduler instance.

## Mandatory go-live information (kept in server secrets, NEVER shared in ChatGPT)

1. Telegram BotFather token and HTTPS webhook hostname.
2. Numeric chat IDs of the **test** channel and optional test groups, followed by production IDs after owner sign-off.
3. Numeric owner/admin Telegram IDs and roles (`TELEGRAM_OWNER_USER_IDS`, `TELEGRAM_EDITOR_USER_IDS`, `TELEGRAM_APPROVER_USER_IDS`, `TELEGRAM_PUBLISHER_USER_IDS`). Developers need server maintenance access, **not** content approval by default.
4. Telegram webhook secret and admin API token.
5. Verified prayer Zoom link (`ZOOM_PRAYER_URL`) and private mentorship class link (`PAID_MENTORSHIP_URL`), stored as server secrets.
6. Channel-authorized YouTube OAuth client, refresh token and app credentials for true live detection.
7. Wix event API read token/site ID for public schedule data (optional in first pilot).
8. Owner approval before enabling `AUTO_APPROVE_LIVE_ALERTS`, `AUTO_APPROVE_ROUTINE_REMINDERS`, and lastly `LIVE_SENDING_ENABLED`.

**Important:** Your Mint Mobile number's ordinary SMS does NOT follow forwarded voice calls to Google Voice. Phone/SMS setup is a separate workstream.

## Owner/Developer acceptance demonstration

1. As a member, DM the bot `/start`, choose morning prayer, view `/status`, tap the choice twice and confirm on/off, then `/stop` and verify no DM alerts arrive.
2. Join a test mentorship group and receive a welcome. Verify joining unrelated groups does nothing.
3. As an editor, use `/new` to draft; prove the editor **cannot approve**. As an approver, `/preview ID` and `/approve ID`. Prove sending fails with `LIVE_SENDING_ENABLED=false`.
4. With **test-channel IDs only**, explicitly enable sending; publisher sends approved draft; sending again must fail.
5. Add a fake future public Wix event. It must be held for verified date, time, link and owner approval. Generate campaign drafts. Change the link and prove old campaign approvals are invalidated.
6. Test YouTube detection on the authenticated owner channel using an actual private/unlisted livestream visible to the channel OAuth scope. Unknown titles remain held. Auto-approval is OFF unless explicitly approved.
7. Run a simulated network failure during personal delivery; confirm partial delivery audit and no blind retries.
8. Verify the paid mentorship URL goes only to the paid group.
9. Show audit log, backup/restore method, and how to disable the bot in an emergency (`LIVE_SENDING_ENABLED=false` and webhook removal if needed).

## What's outside this v2 bot

- Public websites / branded intake form → Google Sheets (separate developer task).
- Full Instagram Trial Reels video cutting, carousel rendering, publishing and performance-learning system (separate AI Content Studio component).
- Direct Clearstream SMS or WhatsApp sending, which needs separate channel opt-in and provider-specific integration.
- Hosting, SSL, provider credentials, real group/chat IDs: must be configured by your developer. **We have not connected real accounts or confirmed a production launch.**

## Division of responsibility

**Prophet Prosper:** policy owner, final approval delegation, authorizes production activation and changes.
**Michelle:** operational schedule, approves routine communications only if formally delegated, manages follow-ups and alerts.
**Developer:** installation, bot API, server, monitoring, bug fixes and backups; does not receive default content-publishing or private member permissions.
**Moderators:** chat safety, collect issues, draft permitted announcements when assigned.

Don't upload `.env`, member databases, bot tokens, OAuth refresh tokens, or real phone-number lists into ChatGPT or the developer's shared project.
