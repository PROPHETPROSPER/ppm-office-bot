PPM OFFICE BOT — GROUP COMMAND FIX v5

This is a SMALL PATCH to the existing PRIVATE GitHub repository
https://github.com/prophetprosper/ppm-office-bot

What changed
  app/telegram.py: routes Office Bot group messages into the new secure group handler; richer private administrative summaries.
  app/office_group.py: new owner-only group linking, group commands /today /schedule /team /pending /status.
  tests/test_office_group.py: security and functional tests.

UPLOAD
  1. Extract the ZIP; do not upload the ZIP itself.
  2. In your private GitHub repo on branch main, choose Add file > Upload files.
  3. Drag the app and tests FOLDERS from inside the extracted patch directly onto the upload area.
  4. Verify GitHub places app/telegram.py and app/office_group.py in existing app/ (not app/app/).
  5. Commit your changes. If the GitHub interface refuses an existing-file replacement, use GitHub Desktop or git (or a GitHub editor); do not put the ZIP into the repository.
  6. Railway auto-builds from main. Wait for SUCCESS before testing.

INITIAL GROUP SETUP AFTER DEPLOY
  A. In the private Telegram staff group, from the ministry owner Telegram account, send /linkoffice@PPMOfficeBot
  B. Expect 'PPM OFFICE GROUP CONNECTED'.
  C. Send /today@PPMOfficeBot, then /schedule@PPMOfficeBot.
  D. For staff to use shared commands, individually set each confirmed staff person's numeric Telegram ID in TELEGRAM_EDITOR_USER_IDS in Railway. No one becomes admin merely by joining a group.
  E. /new /queue /approve /send remain private-DM-only. Publishing stays OFF.

No bot tokens, staff contact records, or other secrets in this patch.
Local tests: 42 passed on October 12, 2026.
