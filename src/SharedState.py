from micropython import const

# TODO use const else where
WarpedVersion = const("1.1.0")

# TODO isn't used anywhere and should probably be "VECTOR" anyway with system 9
WarpedCodeBase = const("SYSTEM11")

# counts game start cycles
gameCounter = 0

# result of update operation
update_load_result = None

# install fault flag
faults = []

# game data  (speicifc title data)
gdata = {}

# game status
game_status = {}
