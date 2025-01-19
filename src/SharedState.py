from micropython import const

# TODO use const else where
WarpedVersion = const("0.4.0")
WarpedCodeBase = const("SYSTEM11")

# true false - tournament mode
tournamentModeOn = 0

# counts game start cycles
gameCounter = 0

# result of update operation
update_load_result = None

# install fault flag
faults = []

# game data  (speicifc title data)
gdata = {}
