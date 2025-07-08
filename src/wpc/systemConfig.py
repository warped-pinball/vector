vectorSystem = "wpc"
updatesURL = "http://software.warpedpinball.com/vector/wpc/latest.json"

# Firmware version for the WPC build
SystemVersion = "0.0.1"

safe_defaults = {
    "GameInfo": {"GameName": "Generic System", "System": "X"},
    "Definition": {"version": 1},
    "Memory": {"Start": 1, "Length": 8192, "NvStart": 2048, "NvLength": 2048},
    "BallInPlay": {"Type": 0},
    "InPlay": {"Type": 0},
    "DisplayMessage": {"Type": 0},
    "Adjustments": {"Type": 0},
    "HighScores": {"Type": 0},
    "HSRewards": {"Type": 0},
    "Switches": {"Type": 0},
    "CoinDrop": {"Type": 0},
}
