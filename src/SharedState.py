from micropython import const

# TODO use const else where
WarpedVersion = const("1.0.0")
WarpedCodeBase = const("SYSTEM11")

# counts game start cycles
gameCounter = 0

# result of update operation
update_load_result = None

# install fault flag
faults = []

# game data  (speicifc title data)
gdata = {}

# ip address
ipAddress = 0


tournamentModeOn = 0
