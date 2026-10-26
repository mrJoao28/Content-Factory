from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, reset_tzpath

from factory.config import settings


def test_calendar_timezone_without_operating_system_iana_database(client, monkeypatch):
    # Windows normally relies on the declared tzdata package rather than /usr/share/zoneinfo.
    import zoneinfo

    previous = zoneinfo.TZPATH
    reset_tzpath(())
    ZoneInfo.clear_cache()
    try:
        assert datetime(2026, 10, 26, tzinfo=ZoneInfo("America/Manaus")).utcoffset() == timedelta(hours=-4)
        assert client.patch("/settings", json={"timezone": "America/Manaus"}).status_code == 200
    finally:
        reset_tzpath(previous)
        ZoneInfo.clear_cache()


def test_doctor_reports_direct_provider_readiness(client, monkeypatch):
    from factory import chatgpt, doctor

    monkeypatch.setattr(settings, "ai_provider", "chatgpt")
    monkeypatch.setattr(doctor, "auth_status", lambda: (_ for _ in ()).throw(AssertionError("Codex invoked")))
    connection = {"state": "DISCONNECTED", "accounts": [], "active_id": None}
    monkeypatch.setattr(chatgpt.accounts, "status", lambda: connection)
    assert client.get("/doctor").json()["text_provider"]["state"] == "DISCONNECTED"
    connection.update(state="CONNECTED", accounts=[{"active": True, "model": None}])
    assert client.get("/doctor").json()["text_provider"]["state"] == "WAITING_FOR_MODEL"
    connection["accounts"][0]["model"] = "fixture-model"
    assert client.get("/doctor").json()["text_provider"]["state"] == "READY"
    connection.update(state="STORAGE_UNAVAILABLE", message="Configure secure OS storage.")
    assert client.get("/doctor").json()["text_provider"] == {
        "state": "STORAGE_UNAVAILABLE",
        "note": "Configure secure OS storage.",
    }
