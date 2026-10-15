from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def coin_state(monkeypatch):
    pytest.importorskip("reflex")
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parent.parent / "frontend"))
    from frontend.state import coin_state

    return coin_state


def test_coin_alert_groups_sort_highest_target_first(coin_state):
    alerts = [
        {"direction": "above", "price": 2.0},
        {"direction": "below", "price": 3.0},
        {"direction": "above", "price": 9.0},
        {"direction": "below", "price": 8.0},
    ]
    state = SimpleNamespace(coin_alerts=alerts)

    above = coin_state.CoinState.__dict__["coin_alerts_above"].fget(state)
    below = coin_state.CoinState.__dict__["coin_alerts_below"].fget(state)

    assert [alert["price"] for alert in above] == [9.0, 2.0]
    assert [alert["price"] for alert in below] == [8.0, 3.0]
