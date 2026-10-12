# Developer checklist — PPM Telegram Bot v2

## Priority 1: Set up private staging (not production)
1. Keep code in a ministry-owned private repository. Use controlled developer access, never shared owner passwords.
2. Start a bot via @BotFather on an **owner-controlled Telegram account**. Store token in server secrets, not in the shared project.
3. Create a separate test channel and test groups. Grant the minimum necessary bot posting permissions.
4. Deploy the FastAPI app, scheduler, database and HTTPS webhook. Use a persistent encrypted/backed-up volume for database.
5. Set `LIVE_SENDING_ENABLED=false`, `AUTO_APPROVE_LIVE_ALERTS=false`, `AUTO_APPROVE_ROUTINE_REMINDERS=false`.
6. Enter test chat IDs, an owner numeric Telegram ID, editor and approver test IDs. Verify user IDs are numeric.
7. Run `pytest -q`. Ensure all tests pass. Verify the webhook secret rejects invalid requests.

## Priority 2: Acceptance tests with owner
8. Subscribe/unsubscribe twice using an actual Telegram user; duplicate callbacks must not invert preferences.
9. Ask Michelle/editor to create `/new`; ensure no posting occurs. Ask a separate approver to review and approve. Verify publisher cannot send unapproved draft.
10. Owner enables sending with **test IDs only**. Confirm one approved post arrives once; no duplicate on repeat command.
11. Add bot to two test groups and confirm welcome messages only in authorized groups.
12. Connect real channel-authorized YouTube OAuth credentials; test detecting a live stream. Check hold for unknown titles.
13. Validate prayer Zoom URL and private mentorship link, then generate daily reminders with safe destinations.
14. Import a test Wix event. Approve after confirming public website time/link. Change website details and verify announcements are put on hold.
15. Simulate mid-send error. Confirm `NEEDS_MANUAL_REVIEW` and no automatic duplicate retry.

## Priority 3: Production rollout — owner approval required
16. Owner explicitly approves production switch. Replace test destinations with verified production numeric channel/group IDs.
17. Use a private production dry run with send disabled. Obtain written go-live approval for each publishing policy.
18. Turn on `LIVE_SENDING_ENABLED=true` only after audit. Keep auto-approve policies off until separately authorized.
19. Monitor 24–48h before increasing automatic posting. Maintain daily database backup and alert for stale/failed messages.
20. Give owner credentials/role management and a maintenance runbook; developer must never be the only person capable of stopping or restoring the bot.

## Separate next tasks, after bot pilot
- Wix `/connect` branded intake form → private Google Sheets → QR code and follow-up roster.
- PPM AI Content Studio: one sermon → 3-slide carousel + 1–2 reels, separate AI review, explicit approval, Trial Reels scheduling, performance measurements.
- Consent-managed Clearstream SMS / WhatsApp. They are export/review-only in bot v2.
- Office calls: Mint-to-Google-Voice call forwarding is voice-only; shared SMS needs a different plan.

## Weekly proof required by ministry owner
Show the Telegram bot working in real private test chats, subscriber topic toggles, separate roles, a verified active livestream alert, and the complete approve-to-send pathway. Send screenshots and a brief test report including which integrations are still blocked.
