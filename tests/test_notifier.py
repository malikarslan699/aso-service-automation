from types import SimpleNamespace

from app.services import notifier


def test_send_suggestion_alert_accepts_orm_like_objects(monkeypatch):
    sent = {}

    monkeypatch.setattr(notifier, "_get_bot_config", lambda db: ("token", "chat"))
    monkeypatch.setattr(
        notifier,
        "_send_message",
        lambda bot_token, chat_id, text: sent.update({"text": text}) is None,
    )

    ok = notifier.send_suggestion_alert(
        [SimpleNamespace(field_name="title", risk_score=3)],
        "Demo App",
        db=None,
    )

    assert ok is True
    assert "title" in sent["text"]
