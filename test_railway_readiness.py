"""Tests for deployment configuration, without starting Telegram or spending money."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.storage import db_file, init_db


def test_railway_volume_path(monkeypatch, tmp_path):
    monkeypatch.delenv('DB_PATH', raising=False)
    monkeypatch.setenv('PPM_DATA_DIR', str(tmp_path))
    assert db_file() == str(tmp_path / 'ppm.sqlite3')
    init_db()
    assert (tmp_path / 'ppm.sqlite3').exists()


def test_readiness_requires_admin_and_reports_no_secrets(monkeypatch,tmp_path):
    monkeypatch.setenv('APP_ADMIN_TOKEN','strong-test-admin-token')
    monkeypatch.setenv('DB_PATH',str(tmp_path/'readiness.db'))
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN','very-secret-bot-token')
    monkeypatch.setenv('TELEGRAM_WEBHOOK_SECRET','webhook-secret')
    monkeypatch.setenv('LIVE_SENDING_ENABLED','false')
    monkeypatch.setenv('PPM_SCHEDULER_ENABLED','false')
    init_db()
    cli=TestClient(app)
    assert cli.get('/admin/readiness').status_code == 401
    r=cli.get('/admin/readiness',headers={'Authorization':'Bearer strong-test-admin-token'})
    assert r.status_code==200
    body=r.json()
    assert body['telegram_outbound_enabled'] is False
    assert body['scheduler_enabled'] is False
    assert body['db_storage_directory_writable'] is True
    assert 'very-secret-bot-token' not in r.text
    assert 'webhook-secret' not in r.text
