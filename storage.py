import sqlite3, os, json, datetime
from contextlib import contextmanager
from app.settings import setting

def db_file():
    explicit=setting('DB_PATH')
    if explicit:return explicit
    data_dir=setting('PPM_DATA_DIR')
    if data_dir:return os.path.join(data_dir,'ppm.sqlite3')
    return 'ppm.sqlite3'

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

@contextmanager
def connect():
    db=sqlite3.connect(db_file(),timeout=10)
    db.row_factory=sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    try:
        yield db
        db.commit()
    finally:
        db.close()

def init_db():
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS members (
            telegram_id INTEGER PRIMARY KEY, first_name TEXT, started_at TEXT NOT NULL,
            stopped_at TEXT, last_seen_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS preferences (
            telegram_id INTEGER NOT NULL REFERENCES members(telegram_id),
            topic TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(telegram_id,topic));
        CREATE TABLE IF NOT EXISTS wix_sources (
          event_id TEXT PRIMARY KEY, source_fingerprint TEXT NOT NULL,
          checked_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS event_subscriptions (
            telegram_id INTEGER NOT NULL REFERENCES members(telegram_id),
            event_id TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY(telegram_id,event_id));
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY, name TEXT NOT NULL, start_date TEXT NOT NULL,
            end_date TEXT, time_label TEXT, url TEXT NOT NULL, topic TEXT NOT NULL,
            public_ok INTEGER NOT NULL DEFAULT 0, is_private INTEGER NOT NULL DEFAULT 0,
            review_reason TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS drafts (
            draft_id INTEGER PRIMARY KEY AUTOINCREMENT, dedupe_key TEXT UNIQUE NOT NULL,
            event_id TEXT, audience TEXT NOT NULL, topic TEXT NOT NULL,
            text TEXT NOT NULL, scheduled_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'DRAFT',
            created_at TEXT NOT NULL, approved_by TEXT, approved_at TEXT, sent_at TEXT,
            last_error TEXT, metadata_json TEXT DEFAULT '{}');
        CREATE TABLE IF NOT EXISTS audits (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL,
            details TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_sessions (
            telegram_id INTEGER PRIMARY KEY, step TEXT NOT NULL, audience TEXT,
            topic TEXT, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS processed_telegram_updates (
            update_id INTEGER PRIMARY KEY, status TEXT NOT NULL, seen_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS telegram_deliveries (
            draft_id INTEGER NOT NULL REFERENCES drafts(draft_id),
            telegram_id INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'PENDING',
            updated_at TEXT NOT NULL, last_error TEXT,
            PRIMARY KEY (draft_id, telegram_id));
        CREATE TABLE IF NOT EXISTS ai_assets (
            asset_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL, teaching_ref TEXT NOT NULL,
            asset_json TEXT NOT NULL, quote_check TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'REVIEW_REQUIRED');
        ''')

def audit(actor, action, details):
    with connect() as db:
        db.execute('INSERT INTO audits(created_at,actor,action,details) VALUES(?,?,?,?)',
                   (now_iso(),actor,action,json.dumps(details,ensure_ascii=False)[:4000]))

def rows(sql, params=()):
    with connect() as db:
        return [dict(row) for row in db.execute(sql,params).fetchall()]
