VectorVersion = "1.11.27"



# counts game start cycles
gameCounter = 0

# result of update operation
update_load_result = None

# install fault flag
faults = []

# cached wifi connection state, kept up to date by backend.connect_to_wifi() -
# lets code that just wants to display status (e.g. faults.update_led_sequence)
# avoid polling the network/cyw43 driver directly
wifi_connected = False

# cached AP-vs-app mode, set once in backend.go() - lets code that just wants
# to display status avoid calling into the HTTP route-handler machinery
# (route_wrapper() runs gc.collect() on every call, which is not cheap)
ap_mode = False

# game data  (speicifc title data)
gdata = {}

# game status
game_status = {}
