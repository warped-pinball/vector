import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.common.personal_bests import compute_personal_bests


def test_compute_personal_bests():
    players = {
        "0": {"initials": "AAA", "full_name": "Alice"},
        "1": {"initials": "BBB", "full_name": "Bob"},
    }
    scores = {
        "0": [
            {"score": 100, "date": "01/01/2024"},
            {"score": 200, "date": "01/02/2024"},
        ],
        "1": [
            {"score": 50, "date": "01/01/2024"},
            {"score": 300, "date": "01/03/2024"},
        ],
    }
    result = compute_personal_bests(players, scores)
    assert result[0]["id"] == 1
    assert result[0]["score"] == 300
    assert result[0]["rank"] == 1
    assert result[1]["id"] == 0
    assert result[1]["score"] == 200
    assert result[1]["rank"] == 2
