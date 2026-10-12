# Ministry data governance

- Do not store counseling information, donations, sensitive prayers, medical records, or minors' information in public Telegram bot subscriptions.
- For Telegram use numeric user IDs and chosen alert topics only; /stop removes subscriptions. Decide and publish a real retention/deletion policy before collecting personal information.
- Wix account read-only permissions for events. Every new/changed event is held until the title, date, public link and program time are reviewed.
- YouTube authenticated OAuth only; live detections become review drafts.
- Clearstream SMS: contacts must have consent for messages; import no legacy contacts without verifying permission. Messages are exported for human review, never automatically sent in this v1 code.
- WhatsApp: separate opt-in, compliant template messages outside the conversation window, manual review/export only.
- Temporary office calling: Mint call forwarding may route calls, but Mint SMS does not become a shared Google Voice inbox. Protect the office number; do not share account logins. Separate permanent shared-calling solution later.
- Strictly no MoreThanPanel orders: only service catalog and balance read functions exist, and approval UI has no order pathway. Use hypothetical metrics comparison, not fake engagements.
- Confidential PPP Dallas and relocation intentions: never place in this database or the public event register; manage in a separate owner-only system.
- Staff: each approved person receives their own access, least privilege, role training and removal process. Revoke access upon exit.
- API: HTTPS reverse proxy, strong APP_ADMIN_TOKEN, Telegram webhook secret, secrets manager, database backups, server access control and monitoring are deployment prerequisites.
- SQL uses parameterized queries. Audit records log workflow decisions but do not contain API keys.
- For personal Telegram event reminders the system sends only to members who clicked `/start` and explicitly selected that event. The dispatch cap is 100 recipients per approved message in this v1; larger audiences require a durable recipient-level queue with throttling and retry safety.
- For real production, add deletion/retention automation, encrypted backups and per-role administrator permissions rather than a shared admin token.
