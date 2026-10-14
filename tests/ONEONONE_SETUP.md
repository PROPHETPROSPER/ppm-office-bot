# Wix 1-on-1 intake for the existing PPM Office Bot

This integration extends the existing PPM Office Bot source based on GitHub main commit ae6cd52. New intake, polling and staff-alert gates default to false. No production credentials, staff IDs, private registration records, or tokens are included. Installation alone does not establish live Wix/Google connections or staff delivery.

The Docker image copies `app/`, so changes are made there. The unrelated duplicate files at repository root are preserved. Existing staff roles, source files, and campaign settings are preserved.

## Behavior

- Read all three known Wix collections: `contact12`, `Forms/contact12`, `Forms/contact122`, on site `9ce2c32c-6895-4799-9bd5-49bbb8cd0f53`.
- Require field IDs verified against each live collection schema, including the actual Submission Time field. Never substitute Created Date or processing time.
- Target only spreadsheet `1dCldUJxv9shtJFifidkZjmWakZpOsyjChFpMb0n1N6o`, tab `Wix 1on1 Registrations`. Require the current 27 headers exactly before writing.
- Establish a silent historical baseline only after every source ID is present in the existing sheet. Baseline is one-time and cannot be reset through this feature.
- Append new IDs with literal values; preserve all existing rows, consent, call history and follow-up fields. Never merge separate Wix IDs by email or phone.
- Hold missing/invalid contact information, invalid/future timestamps, test identities and conflicting/changed source records for manual review. Older records found after baseline remain silent.
- Eligible new requests produce a private Michelle notice only after the dedicated staff-alert gate and existing live-send gate are enabled.
- Michelle gets Send to Crystal, View Registration, Disregard. View Registration opens the existing sheet tab. Routing creates one durable assignment; repeated clicks do not create duplicate assignments.
- Crystal gets Accept Assignment, Contacted, Follow Up, Scheduled. These are staff-reported statuses held in the bot database. This version does not overwrite the sheet's existing follow-up columns with those statuses.
- Callbacks require the configured approved staff account, a private chat, and the stored message ID. Names/usernames do not grant access. No staff access is added automatically.
- Never send to leads or broadcast destinations. Telegram callback payloads contain only opaque references and action names.
- Persist an uncertain state before network writes/sends. A response timeout or process crash cannot cause a blind repeated append or Telegram send. Operators must reconcile uncertain notices against Telegram before any future retry mechanism is introduced.

## Private configuration

Configure secrets only through the existing secure provider mechanism, never in chat, source, the archive or this document.

| Setting | Purpose |
| --- | --- |
| `WIX_1ON1_API_TOKEN` | Existing authorized Wix access with permission to read the three collections. Live legacy/app-collection access must be verified. |
| `PPM_1ON1_WIX_FIELD_MAP` | JSON mapping keyed by the three collection IDs. Each contains real field IDs for `submitted_at`, `first_name`, `phone`, `email`, `country`, and optional `last_name`. CSV labels are not assumed to be field IDs. |
| `GOOGLE_SHEETS_CLIENT_ID`, `GOOGLE_SHEETS_CLIENT_SECRET`, `GOOGLE_SHEETS_REFRESH_TOKEN` | Existing authorized Google OAuth credentials with write access to the exact spreadsheet. ChatGPT connector access is not a server runtime credential. |
| `GOOGLE_SHEETS_ACCESS_TOKEN` | Optional short-lived test alternative; refresh credentials are preferred for sustained operation. |
| `PPM_1ON1_MICHELLE_USER_ID` | Verified numeric account already approved as an office coordinator. |
| `PPM_1ON1_CRYSTAL_USER_ID` | Verified distinct numeric account already approved as an office worker/coordinator. |
| `PPM_1ON1_TEST_EMAILS` | Optional private comma-separated known test/owner identities; no real addresses embedded in source. |
| `PPM_1ON1_ENABLED` | Default false. Enables intake/baseline processing. Does not enable staff delivery by itself. |
| `PPM_1ON1_POLLING_ENABLED` | Default false. Runs the dedicated poller independently of the existing campaign scheduler. |
| `PPM_1ON1_STAFF_ALERTS_ENABLED` | Default false. Enable only after reviewing the exact staff message preview and approval. |
| `PPM_1ON1_POLL_SECONDS` | Default 300, minimum 60. |

Staff delivery additionally requires the existing `LIVE_SENDING_ENABLED` gate. Do not change that shared gate without inspecting its current behavior: it also controls other bot features. Do not enable the campaign scheduler as a shortcut for this feature.

No new credential, app connection, permission grant, or staff-access expansion was made. Obtain approval if new security-sensitive access is needed. Both staff accounts must have opened the bot privately so Telegram can deliver their notices.

## Protected operator routes

All routes use the bot's existing bearer `APP_ADMIN_TOKEN` authentication:

- `GET /admin/1on1/status`: aggregate states, pending/uncertain counts, gate status, baseline status. No contact details or tokens.
- `POST /admin/1on1/baseline`: complete source/Sheet verification and silent historical baseline. Never sends notices.
- `POST /admin/1on1/sync`: reconcile source IDs, append missing new records, queue eligible notices. Never sends notices itself.
- `POST /admin/1on1/deliver-staff-notices`: explicit private staff delivery behind all gates and identity/recipient checks.

Use one Railway replica with the existing persistent SQLite volume. The separate opt-in poller performs sync then gated delivery. It refuses to operate without a completed baseline. No public webhook or anonymous intake endpoint is added.

## Before any deployment or activation

1. Review the patch and confirm the GitHub main version has not changed since ae6cd52. Preserve any newer work and Railway runtime patches.
2. Verify live Wix schema IDs and source access for every collection; Form 2 still needs a verified schema even though it currently has zero submissions.
3. Securely configure existing runtime credentials and verify the exact Sheet headers and permission. Do not broaden sharing to make writes work.
4. Confirm both staff identities and existing roles. No names are resolved automatically.
5. Keep all new gates false during deployment review. A push to the deployment branch may automatically deploy; do not push the deployment branch without approval.
6. When authorized, enable intake only, establish the silent baseline, and inspect protected counts. Current sheet has 57 records; 46 are authoritative historical Wix imports. Prior incomplete/test entries remain preserved.
7. Review synthetic previews and perform an approved private staff test before enabling notices. Existing tests use only fake providers; no real delivery is verified yet.

## API references

- Wix query-data-items: https://dev.wix.com/docs/api-reference/business-solutions/cms/data-items/query-data-items
- Wix maintained request examples: https://github.com/wix/skills/blob/main/skills/wix-manage/references/cms/cms-data-items-crud.md
- Google Sheets literal-value append: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/append

## Limitations

Live provider credentials, Wix field mapping and Telegram recipients are unconfigured. Runtime API permissions for the two Wix app collections must still be tested. Unknown or changed source records are held rather than overwriting old Sheet rows. There is no automatic retry/reset for ambiguous delivery, no automatic lead contact, and no live proof of this integration. Google runtime OAuth access requires its own authorized setup; the current ChatGPT Google connector cannot be reused as a server secret.
