"""Schema definitions for JSON config validation.

Keep this file data-only so it's easy to extend when new settings are added.
"""

SCHEMA_RULES = [
    {
        "name": "em-game-config",
        "include": ["src/em/config/*.json"],
        "required": {
            "GameInfo": ["GameName", "System"],
        },
    },
    {
        "name": "standard-game-config",
        "include": [
            "src/sys11/config/*.json",
            "src/wpc/config/*.json",
            "src/data_east/config/*.json",
        ],
        "required": {
            "GameInfo": ["GameName", "System"],
            "Memory": ["Start", "Length", "NvStart", "NvLength"],
            "BallInPlay": ["Type"],
            "DisplayMessage": ["Type"],
            "Adjustments": ["Type"],
            "HighScores": ["Type"],
        },
    },
]
