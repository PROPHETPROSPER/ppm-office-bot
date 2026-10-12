# PPM Bot — Owner activation, not developer setup

**Current state on Oct 12, 2026:** Python bot has passed unit tests. Railway's existing `PPM Private Test` project holds **staged** infrastructure, not a running deployment. All public sending and automatic scheduling remain disabled. No Telegram bot has been registered through BotFather in this conversation.

## The one step only you can do in Telegram

1. Open the verified Telegram account [@BotFather](https://t.me/BotFather).
2. Send `/newbot`.
3. Display name: **Prophet Prosper Ministries**.
4. Pick an available username, e.g. `ProphetProsperMinistryBot` (Telegram requires usernames to end in `bot`).
5. Save the token privately. **Do not paste it into ChatGPT, a shared project, or a volunteer chat.** Keep it until the hosting service is ready to accept a secret.
6. Reply here with **only the public `@bot_username`**. The bot token should be entered through Railway's secure Variables panel, not this conversation.

The assistant can then continue deployment configuration and live integration tests, using owner-controlled resources.

## What's left for live service

- Add the approved bot code to a private GitHub repository connected to Railway, or deploy it using Railway's CLI under the owner's account. Railway's current project has a staged service **without any source code attached**.
- Set secure env variables: bot token, verified test channel/group numeric IDs, owner Telegram numeric user ID, webhook signing secret, API admin secret, and exact Zoom links.
- Confirm all approved chat IDs refer to **test communities** before setting the Telegram webhook and enabling sending.
- Finish Google YouTube OAuth and Wix authorization for active livestream and event syncing.
- Accept and deploy the existing non-destructive Railway staging patch **only after the source and secrets are present**. The current bot code does not have its own GitHub repository connected.
- Demonstrate `/start`, `/alerts`, `/new`, review/approve, a single test delivery, actual live detection, and audit logs.

## Safety settings

- `LIVE_SENDING_ENABLED=false` (default)
- `PPM_SCHEDULER_ENABLED=false` (default)
- `AUTO_APPROVE_LIVE_ALERTS=false` (default)
- `AUTO_APPROVE_ROUTINE_REMINDERS=false` (default)
- `DB_PATH=/var/data/ppm.sqlite3` with Railway volume mounted at `/var/data`
- Single replica only. The in-container scheduler is supported via `PPM_SCHEDULER_ENABLED=true` when deliberately activated.

The bot cannot be created via Telegram's Bot API alone. Official BotFather registration must come from an authenticated Telegram user account.
