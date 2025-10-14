import importlib
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def em_game_status(monkeypatch):
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root / "src" / "common"))
    monkeypatch.syspath_prepend(str(repo_root / "src" / "em"))

    # Stub logger
    fake_logger = types.ModuleType("logger")

    class DummyLogger:
        def __init__(self):
            self.messages = []

        def log(self, message):
            self.messages.append(message)

    fake_logger.logger_instance = DummyLogger()
    monkeypatch.setitem(sys.modules, "logger", fake_logger)

    # Stub ScoreTrack
    fake_scoretrack = types.ModuleType("ScoreTrack")
    scores = [111_000, 222_000, 333_000, 444_000]

    def get_player_score(index):
        return scores[index]

    fake_scoretrack.getPlayerScore = get_player_score
    monkeypatch.setitem(sys.modules, "ScoreTrack", fake_scoretrack)

    # Stub sensorRead
    fake_sensor = types.ModuleType("sensorRead")
    fake_sensor._state = 0

    def game_active():
        return fake_sensor._state

    fake_sensor.gameActive = game_active
    monkeypatch.setitem(sys.modules, "sensorRead", fake_sensor)

    # Stub origin module
    fake_origin = types.ModuleType("origin")

    class FakeConfig:
        def __init__(self):
            self.enabled = False

        def is_enabled(self):
            return self.enabled

    fake_origin.config = FakeConfig()
    fake_origin.push_calls = []
    fake_origin.push_game_state = lambda **_: None
    monkeypatch.setitem(sys.modules, "origin", fake_origin)

    GameStatus = importlib.import_module("GameStatus")
    monkeypatch.setattr(GameStatus, "sensorRead", fake_sensor, raising=False)
    monkeypatch.setattr(GameStatus, "ScoreTrack", fake_scoretrack, raising=False)

    push_calls = []

    def record_push(**kwargs):
        push_calls.append(kwargs)

    monkeypatch.setattr(GameStatus, "push_game_state", record_push)

    class TickCounter:
        def __init__(self):
            self.value = 0

        def tick(self):
            self.value += 100
            return self.value

    ticker = TickCounter()
    monkeypatch.setattr(GameStatus, "_ticks_ms", ticker.tick)

    GameStatus.S.game_status = {
        "game_active": False,
        "number_of_players": 0,
        "time_game_start": None,
        "time_game_end": None,
        "poll_state": 0,
    }

    return {
        "module": GameStatus,
        "push_calls": push_calls,
        "sensor": fake_sensor,
        "scores": scores,
    }


def test_poll_fast_no_origin_push_when_disabled(em_game_status):
    gs = em_game_status["module"]
    push_calls = em_game_status["push_calls"]
    sensor = em_game_status["sensor"]

    gs.origin_config.enabled = False
    sensor._state = 1
    gs.poll_fast()

    assert push_calls == []


def test_poll_fast_pushes_scores_when_enabled(em_game_status):
    gs = em_game_status["module"]
    push_calls = em_game_status["push_calls"]
    sensor = em_game_status["sensor"]
    scores = em_game_status["scores"]

    gs.origin_config.enabled = True
    sensor._state = 1
    gs.poll_fast()

    assert len(push_calls) == 1
    payload = push_calls[0]
    assert payload["scores"] == scores
    assert payload["ball_in_play"] == 1
    assert payload["game_time"] == 0
    assert gs.S.game_status["game_active"] is True


def test_poll_fast_pushes_game_end_state(em_game_status):
    gs = em_game_status["module"]
    push_calls = em_game_status["push_calls"]
    sensor = em_game_status["sensor"]

    gs.origin_config.enabled = True

    # Start game
    sensor._state = 1
    gs.poll_fast()

    # End game
    sensor._state = 0
    gs.poll_fast()

    assert len(push_calls) == 2
    end_payload = push_calls[-1]
    assert end_payload["ball_in_play"] == 0
    assert end_payload["game_time"] == 0
    assert gs.S.game_status["game_active"] is False
