# PPM Telegram admin bot — training sheet

The bot operates in **private DM only** for administrators. Each operator gets a Telegram user ID entered into `TELEGRAM_ADMIN_USER_IDS`; never share the owner's Telegram account or bot API token.

## Members

- `/start` — register the bot and choose optional personal notification types. Off by default.
- `/alerts` — change topics: Morning Prayer, evening teaching, Prayer Chain, schools, in-person gatherings, weekly recap.
- `/events` — choose a *specific verified event* for daily countdown reminders during its final three days. Tap again to unsubscribe.
- `/stop` — turn off all bot direct alerts. Group/channel posts may remain visible to subscribed group members.

The bot may welcome a user who joins a private group, but it cannot send the user private messages until they start the bot.

## Staff (approved user IDs only)

- `/draft official|schools|The new prophetic school is open: https://...`
- `/draft free|prayer_chain|This week's prayer study is...`
- `/draft paid|weekly_digest|Saturday Spiritual Foundation notes...`
- `/queue` — preview last eight drafts.
- `/approve 18` — mark draft approved; no sending yet.
- `/send 18` — send only if `LIVE_SENDING_ENABLED=true` and the draft has already been approved. Groups/channels only from Telegram admin commands; personal opt-in messages use the backend protected API/approved schedule.

If someone submits a Dallas reference in the general bot, the message is blocked. Keep confidential events out of this system.

**Daily responsibilities:** Michelle reviews/approves; media volunteers submit actual links/clips; a moderator verifies livestream title/link; a connections assistant monitors opt-in and missed inquiries.
