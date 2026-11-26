"""Shared isolated approval interface for operation-boundary tests."""
import threading
from types import SimpleNamespace

import pytest

from ultron.core import confirm


@pytest.fixture
def operation_hud(monkeypatch):
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    shown, logs = [], []
    finished = threading.Event()

    def log(text):
        logs.append(text)
        if text.startswith(("SYS: Confirmed", "ERR: Confirmed action")):
            finished.set()

    confirm.bind(None, None, log, show_with_id=lambda *args: shown.append(args),
                 hide_with_id=lambda _: None)
    return SimpleNamespace(shown=shown, logs=logs, finished=finished)

