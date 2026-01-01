# Common firmware version shared by all builds
VectorVersion = "1.10.0"
# TODO this should not be duplicated from common/origin.py if we forget to update both places EMs will always think they are out of date


# counts game start cycles
gameCounter = 0

# result of update operation
update_load_result = None

# install fault flag
faults = []

# game data  (specific title data)
gdata = {"numberOfPlayers": 2, "digitsPerPlayer": 4, "dummy_reels": 0}

# game status
game_status = {}


run_learning_game = False
