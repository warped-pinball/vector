# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
Switch monitoring and tracking module.

Tracks switch activity by monitoring which switches have been tripped
and maintains a local count for each switch. Counts are reset when
switches are detected as tripped.

Note: MicroPython uses cooperative multitasking (single-threaded event loop).
Scheduled tasks don't preempt each other, so no synchronization is needed.
"""
import SPI_DataStore
import DataMapper
import SharedState as S
from logger import logger_instance
log = logger_instance

# Local storage for 72 switch counts
switch_counts = [0] * 72

# Poll counter and game state tracking
poll_counter = 0
last_ball_in_play = 0
last_player_up = 0
last_game_active = False

#switch system enable
switch_system_on = False

# Switch subscription system
switch_subscriptions = {}


POLL_SWITCHES_mS = 1700 #5000
POLL_GAME_STATE_CNT = 17


def initialize():
    """
    Initialize the switches module by loading switch counts from SPI storage.
    Should be called once at startup.
    """
    global switch_counts, last_ball_in_play, last_player_up, switch_system_on
    
    if S.gdata.get("Switches", {}).get("Type") != 10:
        log.log("SWITCHES: Invalid or missing 'Switches'")
        switch_system_on = False
        return False

    try:
        record = SPI_DataStore.read_record("switches")     #read from fram switch counts
        switch_counts = record.get("switches", [0] * 72)   #max len is 72, most dont use all
        log.log(f"SWITCHES: Loaded {len(switch_counts)} switches from storage")

        last_ball_in_play = DataMapper.get_ball_in_play()
        last_player_up = DataMapper.get_player_up()
        switch_system_on = True

        # Schedule polling
        from phew.server import schedule
        schedule(poll_switches, 15000, POLL_SWITCHES_mS)

    except Exception as e:
        log.log(f"SWITCHES: Error loading switch counts: {e}")
        switch_counts = [0] * 72


def poll_switches():
    """
    Poll switches to check for tripped status.
    Called periodically (every 5 seconds) to monitor switch activity.
    
    When a switch is detected as tripped (True from get_switches_tripped),
    its local count is reset to zero.
    
    Every X calls, also checks for game state changes (ball_in_play, player_up, game over).
    """
    global switch_counts, poll_counter, last_ball_in_play
    global switch_system_on, last_player_up, last_game_active
    
    if switch_system_on is False:
        return

    try:
        tripped = DataMapper.get_switches_tripped()        
        if not tripped:
            return

        DataMapper.write_switches_nominal()

        # Reset counts for any tripped switches
        # Use enumerate to avoid index errors
        for idx, is_tripped in enumerate(tripped):
            if idx < len(switch_counts) and is_tripped:
                switch_counts[idx] = 0
        
        # Call callbacks only for subscribed switches that are tripped
        for switch_idx, callbacks in switch_subscriptions.items():
            if switch_idx < len(tripped) and tripped[switch_idx]:
                for callback in callbacks:
                    try:
                        callback(switch_idx)
                    except Exception as e:
                        log.log(f"SWITCHES: Error in callback for switch {switch_idx}: {e}")
        
        # Every X calls, check for game state changes (low impact)
        poll_counter += 1
        if poll_counter > POLL_GAME_STATE_CNT:
            poll_counter = 0
            
            # Check for ball_in_play and player_up changes
            current_ball = DataMapper.get_ball_in_play()
            current_player = DataMapper.get_player_up()
            
            if current_ball != last_ball_in_play or  current_player != last_player_up:
                print(f"SWITCHES: Ball change detected. Inc switch counts.")
                last_ball_in_play = current_ball                                   
                last_player_up = current_player
                if last_ball_in_play !=0:
                    switch_counts = [min(count + 1, 251) for count in switch_counts]
                    #for idx in range(len(switch_counts)):
                    #    if switch_counts[idx] < 251:
                    #        switch_counts[idx] += 1

            # game over? time to save to fram?
            game_active=DataMapper.get_game_active()
            if last_game_active is True and game_active is False:
                log.log(f"SWITCHES: Game over, save switches")
                save_switches()
            last_game_active=game_active    
                      
    except Exception as e:
        log.log(f"SWITCHES: Error in poll_switches: {e}")



def save_switches():
    """
    Save the current switch counts to SPI storage.
    """
    global switch_counts
    try:
        # Capture snapshot of counts to avoid partial reads during save
        counts_snapshot = list(switch_counts)
        record = {"switches": counts_snapshot}
        SPI_DataStore.write_record("switches", record)
        log.log("SWITCHES: Saved switch counts to storage")
    except Exception as e:
        log.log(f"SWITCHES: Error saving switch counts: {e}")


def get_switch_index(switch_name):
    """
    Translate a switch name to its index.
    
    Args:
        switch_name: Name of the switch (string)
    
    Returns:
        int: Switch index (0-71) or -1 if not found
    """
    if not switch_system_on:
        return -1
    try:
        names = S.gdata.get("Switches", {}).get("Names")
        if not names:
            return -1
            
        for idx, entry in enumerate(names):
            # Extract name from [name, sensitivity] or plain string
            name = entry[0] if isinstance(entry, list) and entry else entry
            if name == switch_name:
                return idx        
        return -1
    except Exception as e:
        log.log(f"SWITCHES: Error in get_switch_index: {e}")
        return -1


def subscribe(switch_name, callback):
    """
    Subscribe to a specific switch trigger event.
    
    Args:
        switch_name: Name of the switch (string) or switch index (integer) to monitor
        callback: Function to call when switch is triggered. 
                  Callback will receive switch_index as argument.
    
    Returns:
        bool: True if subscription successful, False otherwise
    """
    global switch_subscriptions

    if not callable(callback):
        log.log(f"SWITCHES: subscribe() - callback must be callable")
        return False
    
    # Determine if switch_name is an index or name
    if isinstance(switch_name, int):
        switch_index = switch_name
        max_switch_index=S.gdata["Switches"]["Length"]
        if switch_index < 0 or switch_index > max_switch_index:
            log.log(f"SWITCHES: subscribe() - invalid switch index {switch_index}")
            return False
    else:
        # Translate name to index
        switch_index = get_switch_index(switch_name)
        if switch_index < 0:
            log.log(f"SWITCHES: subscribe() - invalid switch name '{switch_name}'")
            return False
    
    if switch_index not in switch_subscriptions:
        switch_subscriptions[switch_index] = []
    
    if callback not in switch_subscriptions[switch_index]:
        switch_subscriptions[switch_index].append(callback)
        print(f"SWITCHES: Subscribed to switch '{switch_name}' (index {switch_index})")
        return True
    
    return False


def unsubscribe(switch_name, callback):
    """
    Unsubscribe from a specific switch trigger event.
    
    Args:
        switch_name: Name of the switch (string) or switch index (integer) to stop monitoring
        callback: The callback function to remove
    
    Returns:
        bool: True if unsubscription successful, False otherwise
    """
    global switch_subscriptions
    
    # Determine if switch_name is an index or name
    if isinstance(switch_name, int):
        switch_index = switch_name
        if switch_index < 0 or switch_index >= 72:
            log.log(f"SWITCHES: unsubscribe() - invalid switch index {switch_index}")
            return False
    else:
        # Translate name to index
        switch_index = get_switch_index(switch_name)
        if switch_index < 0:
            log.log(f"SWITCHES: unsubscribe() - invalid switch name '{switch_name}'")
            return False
    
    if switch_index not in switch_subscriptions:
        return False
    
    if callback in switch_subscriptions[switch_index]:
        switch_subscriptions[switch_index].remove(callback)
        log.log(f"SWITCHES: Unsubscribed from switch '{switch_name}' (index {switch_index})")
        
        # Clean up empty lists
        if not switch_subscriptions[switch_index]:
            del switch_subscriptions[switch_index]
        
        return True
    
    return False


def get_diagnostics():
    """
    Get diagnostic information for all switches.
    
    Returns a list of switch records with row, col, val (0-100%), and label.
    The val represents how likely the switch is to be functional based on
    how many times it has NOT been hit (switch_counts).
    
    Returns:
        list: List of dicts with keys: row, col, val, label
    """   
    if not switch_system_on:
        return []
    
    try:
        switches_data = S.gdata["Switches"]
        
        # Get switch definitions (either Names or Sensitivity format)
        switch_defs = switches_data.get("Names") or switches_data.get("Sensitivity")
        if not switch_defs:
            log.log("SWITCHES: No 'Names' or 'Sensitivity' found in Switches")
            return []
        
        use_names = "Names" in switches_data
        diagnostics = []
        
        for idx, entry in enumerate(switch_defs[:len(switch_counts)]):
            # Skip -1 entries (marked as unused in config)
            if entry == -1 or entry is None:
                continue
            
            # Extract label and sensitivity
            if use_names and isinstance(entry, list) and entry:
                label = entry[0] or ""
                sensitivity = entry[1] if len(entry) > 1 else 0
            elif not use_names and isinstance(entry, int):
                label = f"Switch {idx+1}"
                sensitivity = entry
            else:
                label = ""
                sensitivity = 0
            
            if not label:
                continue
            
            # Calculate health: 0% at sensitivity, 100% at count=0
            health = 100 if sensitivity == 0 else max(0, 100 - (switch_counts[idx] * 100 // sensitivity))
            
            # Calculate grid position (8 rows per column)
            col, row = divmod(idx, 8)
            diagnostics.append({"row": row + 1, "col": col + 1, "val": health, "label": label})
    
    except Exception as e:
        log.log(f"SWITCHES: Error in get_diagnostics: {e}")
        return []
    
    return diagnostics

