"""Least-privilege Telegram administrative roles configured by numeric Telegram user ID.

Editors can create drafts. Approvers can approve/reject; publishers can send
already approved drafts. Owners do all three. No Telegram chat receives a token.
Legacy TELEGRAM_ADMIN_USER_IDS is treated as 'editor' only, not an implicit approver.
"""
from app.settings import setting

def parse_ids(value):
    return {int(x.strip()) for x in value.split(',') if x.strip().isdigit()}

def role_for(uid):
    if uid in parse_ids(setting('TELEGRAM_OWNER_USER_IDS')): return 'owner'
    if uid in parse_ids(setting('TELEGRAM_APPROVER_USER_IDS')): return 'approver'
    if uid in parse_ids(setting('TELEGRAM_PUBLISHER_USER_IDS')): return 'publisher'
    if uid in parse_ids(setting('TELEGRAM_EDITOR_USER_IDS')) | parse_ids(setting('TELEGRAM_ADMIN_USER_IDS')): return 'editor'
    # Staff membership never grants announcement approval or publishing.
    from app.office_tracker import staff_role
    return staff_role(uid)

def can(uid,action):
    r=role_for(uid)
    return r=='owner' or (r=='editor' and action in ('draft','new','queue','preview')) or \
        (r=='approver' and action in ('approve','reject','queue','preview')) or \
        (r=='publisher' and action in ('send','queue','preview'))
