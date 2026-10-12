# Michelle's Telegram Bot Instructions

**This is for the bot AFTER your developer connects and tests it.** Do not send your main Telegram password to anyone.

## What the bot handles for the ministry
- Welcomes new members in the two private mentorship groups.
- Sends approved events, prayer reminders and teaching alerts.
- Lets people choose which alerts they want without requesting changes from the admin team.
- Creates announcements in a queue so nothing unapproved gets sent.

## Creating a ministry announcement
1. Open the bot privately (DM, not inside a group).
2. Send `/new`.
3. Tap the group/channel where the announcement belongs.
4. Tap the topic (Schools, Prayer Chain, Morning Prayer, etc.).
5. Type or paste the announcement. It will be saved as a **DRAFT**.
6. Tell the approver the draft number. The approver uses `/preview NUMBER` then `/approve NUMBER` (or `/reject NUMBER`).
7. A publisher sends an approved draft with `/send NUMBER`, or an approved time-based scheduler publishes it when due and enabled.

## Checking announcements
- `/queue` — recent announcements and their status.
- `/preview 12` — read the full draft 12.
- An editor cannot approve or send; an approver cannot send unless assigned additional publishing rights. Prophet Prosper determines all role assignments.

## What members can do
- `/start` — join the bot; personal messages require this.
- `/alerts` — choose types of alerts.
- `/events` — choose individual verified public events.
- `/status` — see current choices.
- `/schedule` — current regular ministry schedule.
- `/stop` — stop direct messages from the bot.

## Escalation rules
- If a prayer or personal-care request requires pastoral judgment, refer to Prophet Prosper or an authorized leader.
- Don't forward contact spreadsheets into Telegram chat.
- If an event date, program link or time changes, ask the developer to hold/revalidate old announcements before publishing.
- If the bot fails or sends the wrong message, notify the developer and Prophet Prosper; do not repeatedly resend.
- Don't announce confidential ministry planning without explicit approval.

## End of day report
Send Prophet Prosper a short report: sessions completed; announcements posted; new connections pending follow-up; issues; what needs his approval.
