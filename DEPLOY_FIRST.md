# FIRST DEPLOYMENT — PPM OFFICE BOT

1. **Code location**: Private GitHub repository with `Dockerfile`, `requirements.txt` and `app/` at its root. Never commit `.env` or any real keys.
2. **Railway**: Open `PPM Private Test` → `private-test` → `ppm-bot`, attach GitHub repository as source. Existing service is currently staged without source. Ensure the attached repo matches the current v4 code.
3. **Secrets**: BotFather token is already staged. Add APP_ADMIN_TOKEN, TELEGRAM_WEBHOOK_SECRET, and TELEGRAM_OWNER_USER_IDS privately before the first authenticated webhook test.
4. **Do not enable** `LIVE_SENDING_ENABLED` or `PPM_SCHEDULER_ENABLED` at this stage. Public notifications are not supported in Office mode.
5. **Commit the non-destructive staging patch only after source attached**. Watch for a healthy deployment on `/health`; check `/admin/telegram/identity` as an authorized admin to verify username.
6. **Webhook**: After verified identity, configure Telegram `setWebhook` to `https://<your-railway-domain>/telegram/webhook` with Telegram's `secret_token` matching TELEGRAM_WEBHOOK_SECRET. Never paste this URL with secrets in a public chat.
7. **Owner test**: As owner, /start, /new, draft; prove unauthorized user cannot approve. For a single approved message to a TEST chat, enable `LIVE_SENDING_ENABLED` only after explicit launch approval; immediately disable after test.
8. **Handoff**: Once all tests pass, give developer restricted Railway service maintenance access but no bot publishing role by default.
