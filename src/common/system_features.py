"""Helpers for exposing system-specific feature flags to the web ui."""

from typing import Dict


def get_system_features() -> Dict[str, object]:
    """Return feature flags describing the active Vector system."""
    features: Dict[str, object] = {
        "vector_system": "unknown",
        "requires_game_config": True,
        "supports_adjustment_profiles": True,
        "supports_on_machine_claims": True,
        "supports_web_ui_claims": True,
        "supports_show_ip_on_machine": True,
        "supports_memory_snapshot": True,
        "supports_em_calibration": False,
        "supports_learning_process": False,
        "max_calibration_games": 0,
        "max_machine_name_length": 16,
        "default_score_reels": 4,
    }

    try:
        from systemConfig import vectorSystem  # type: ignore
    except Exception:
        vectorSystem = "unknown"

    features["vector_system"] = vectorSystem

    if vectorSystem == "em":
        features.update(
            {
                "requires_game_config": False,
                "supports_adjustment_profiles": False,
                "supports_on_machine_claims": False,
                "supports_show_ip_on_machine": False,
                "supports_memory_snapshot": False,
                "supports_em_calibration": True,
                "supports_learning_process": True,
                "max_calibration_games": 4,
            }
        )

    return features
