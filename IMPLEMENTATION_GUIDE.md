# Deploy PPM Ministry Automation v1

**Status:** tested prototype, NOT deployed, no credentials connected, no real messages or orders sent.

## Architecture
- `app/main.py`: protected FastAPI administrator endpoints; interactive API at `/docs`.
- `app/telegram.py`: Telegram webhook with topic/event subscriptions, `/start`, `/alerts`, `/events`, `/stop`, group welcome.
- `app/admin_bot.py`: authorized operator's Telegram DM `/draft`, `/queue`, `/approve`, `/send`.
- `app/campaigns.py`: 14/10/7/5/3/2/1/0 event cadence, multi-day continuing messages, daily and weekly limits, approvals and duplicate detection.
- `app/wix_sync.py`: import public Wix events into HOLD when correct public event URL is available; skip owner-only events. Editing an event invalidates queued drafts. Unchanged site events do not wipe editorial approvals.
- `app/worker.py` and `app/scheduler.py`: daily Wix event checks, draft preparation, every-five-minute authenticated YouTube live checks, and dispatch of **already approved** Telegram notices if enabled.
- `app/ai_content.py`: OpenAI or Anthropic sermon transcript to three quote slides and 1–2 reel excerpts, with exact quote checks and editorial review.
- `app/comparison.py`: synthetic or real input conversion funnel scenarios, not a fake-engagement detector.
- `app/integrations.py`: read-only Wix, YouTube, Clearstream account and MoreThanPanel services/balance. **No purchasing code.**

## Local smoke test (no accounts required)
```bash
cd PPM_Ministry_Automation_v1
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Put a random APP_ADMIN_TOKEN in .env, not an example string
pytest -q
uvicorn app.main:app --host 127.0.0.1 --port 8080
```
Open http://127.0.0.1:8080/docs and select Authorize; paste APP_ADMIN_TOKEN as bearer token.

Example `GET /health` shows DRAFT_MODE. `POST /admin/ai/create` with provider=`offline` and an actual sermon transcript generates sample three-slide text without any external AI subscription.

## Docker pilot
```bash
docker compose up --build -d
```
A private HTTPS reverse proxy is mandatory for webhook deployment. The provided Compose port binds to localhost only, not the public internet. Keep only **one** scheduler instance running, backed up with restricted-volume SQLite. n8n can call protected endpoints when connected; the complete service runs without n8n.

## Telegram setup
1. Make a bot using @BotFather. Obtain its token; store in server secret settings, not Telegram messages. Add its username to the group rules.
2. Add bot as an admin to the official public channel and both mentorship groups, granting only needed posting/management permissions.
3. Learn each actual channel/group ID and set environment values `TELEGRAM_OFFICIAL_CHANNEL_ID`, `TELEGRAM_FREE_GROUP_ID`, `TELEGRAM_PAID_GROUP_ID`.
4. Determine Michelle's authorized Telegram numeric ID; add it to `TELEGRAM_ADMIN_USER_IDS`. Don't add volunteers who haven't completed onboarding.
5. Host at a HTTPS endpoint. Configure Telegram `setWebhook` pointing to `https://YOUR-HOST/telegram/webhook`, providing `secret_token` equal to `TELEGRAM_WEBHOOK_SECRET`. Register only required updates (`message`, `callback_query`).
6. Start bot privately; test `/start`, `/alerts`, `/events`, `/stop` from a test Telegram account and verify that a disabled alert never sends.
7. Create a separate test channel first, not your actual public channel. Keep `LIVE_SENDING_ENABLED=false` during all preparation.

## Website events
1. Set Wix API read credential and site ID. `POST /admin/integrations/wix/preview` only displays candidate events; `.../import-on-hold` creates hold records.
2. If Wix does not return a confirmed HTTPS event URL, the event is skipped—**we never invent a website registration link**.
3. Check title, link, actual event date, time and timezone in `GET /admin/events`. Revise with `POST /admin/events`.
4. Approve each verified event using `/admin/events/{id}/approve`, then run `/admin/campaigns/plan`.
5. Approve individual drafts, or inspect the queue in the Telegram bot. `LIVE_SENDING_ENABLED=true` plus approved scheduled Telegram drafts enables delivery. Check audits before production.
6. The 14-day, 7-day and three-day cadence is **not** an invitation to spam all members. Main groups have a three-promotion weekly cap, while personal final-three-day reminders require event-specific bot opt-in.
7. Update the published Watchman Series event page if 2–4 PM ET becomes final; do not approve until matched.

## YouTube
Register a Google Cloud OAuth client with `youtube.readonly` and authorize the owning channel. For long-lived live checks set OAuth client ID, secret and refresh token server-side; never paste tokens into a group. Active YouTube streams are **detected** but announcements are drafts until approved. Edit verified title and correct prayer vs teaching classification before approving.

## AI content
Use `/admin/ai/create` with transcript and exact teaching reference. Set `provider` to `offline`, `openai` or `anthropic`, and supply the model name valid in your API account. OpenAI and Claude API accounts are separate from ChatGPT/Claude subscriptions.

Never send sensitive personal prayer requests to an external AI. Quote verification rejects invented sermon excerpts. Final graphic design and final reel editing remain human tasks.

## Clearstream and WhatsApp
Clearstream has documented REST API and webhooks. This version prepares `APPROVED_EXPORT` records for your trained connections team; it neither imports legacy phone numbers nor sends SMS. WhatsApp is the same. Sending requires confirmed specific consent, unsubscribe handling, templates where necessary, approved sender IDs and a tested provider integration.

## MoreThanPanel and comparison research
`/admin/integrations/morethanpanel/preview` supports ONLY catalog reads. There is no endpoint to place orders, create refills or cancel. `/admin/comparison` takes actual or illustrative metrics for impressions, clicks, voluntary opt-ins, attendance and repeat attendance. These ratios do not prove engagement is fake; they show whether numbers translate to ministry relationships.

## Boundaries and next steps
The connected n8n environments could not be inspected (connector internal errors). No workflows were installed remotely. Before launch, verify server hosting, names/permissions, HTTPS, backups, webhook security, Wix/YouTube credentials, and staff access. Test in a separate Telegram channel first. Be aware the Telegram personal message path supports up to 100 recipients per draft before queue upgrades are required.
