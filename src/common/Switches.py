# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
Switch monitoring and tracking module.

Tracks switch activity by monitoring which switches have been tripped
and maintains a local count for each switch. Counts are reset when
switches are detected as tripped.
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

# Switch subscription system
switch_subscriptions = {}


def init():
    """
    Initialize the switches module by loading switch counts from SPI storage.
    Should be called once at startup.
    """
    global switch_counts, last_ball_in_play, last_player_up
    try:
        record = SPI_DataStore.read_record("switches")
        switch_counts = record.get("switches", [0] * 72)
        log.log(f"SWITCHES: Loaded {len(switch_counts)} switch counts from storage")

        last_ball_in_play = DataMapper.get_ball_in_play()
        last_player_up = DataMapper.get_player_up()

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
    global switch_counts, poll_counter, last_ball_in_play, last_player_up, last_game_active
    
    try:
        tripped = DataMapper.get_switches_tripped()        
        if not tripped:
            return
        
        DataMapper.write_switches_nominal()

        # Reset counts for any tripped switches      
        for idx, is_tripped in enumerate(tripped):
            if idx < len(switch_counts) and is_tripped:                
                switch_counts[idx] = 0
                
                # Call any subscribed callbacks for this switch
                if idx in switch_subscriptions:
                    for callback in switch_subscriptions[idx]:
                        try:
                            callback(idx)
                        except Exception as e:
                            log.log(f"SWITCHES: Error in callback for switch {idx}: {e}")
        
        # Every X calls, check for game state changes (low impact)
        poll_counter += 1
        if poll_counter >= 7:
            poll_counter = 0
            
            # Check for ball_in_play and player_up changes
            current_ball = DataMapper.get_ball_in_play()
            current_player = DataMapper.get_player_up()
            
            if current_ball != last_ball_in_play or  current_player != last_player_up:
                print(f"SWITCHES: Ball change detected. Inc switch counts.")
                last_ball_in_play = current_ball                                   
                last_player_up = current_player
                if last_ball_in_play !=0:
                    for idx in range(len(switch_counts)):
                        if switch_counts[idx] < 251:
                            switch_counts[idx] += 1

            # game over? time to save to fram?
            game_active=DataMapper.get_game_active()
            if last_game_active is True and game_active is False:
                print(f"SWITCHES: Game over, save switches")
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
        record = {"switches": switch_counts}
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
    try:
        if "Switches" not in S.gdata or "Names" not in S.gdata["Switches"]:
            log.log("SWITCHES: No switch names configured in S.gdata")
            return -1
        
        names = S.gdata["Switches"]["Names"]
        for idx, name_entry in enumerate(names):
            # Support list of lists: [name, number]
            if isinstance(name_entry, list) and len(name_entry) > 0:
                name = name_entry[0]
            else:
                name = name_entry
            
            if name == switch_name:
                return idx
        
        log.log(f"SWITCHES: Switch name '{switch_name}' not found")
        return -1
    except Exception as e:
        log.log(f"SWITCHES: Error in get_switch_index: {e}")
        return -1


def subscribe(switch_name, callback):
    """
    Subscribe to a specific switch trigger event.
    
    Args:
        switch_name: Name of the switch to monitor (string)
        callback: Function to call when switch is triggered. 
                  Callback will receive switch_index as argument.
    
    Returns:
        bool: True if subscription successful, False otherwise
    """
    global switch_subscriptions
    
    if not callable(callback):
        log.log(f"SWITCHES: subscribe() - callback must be callable")
        return False
    
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
        switch_name: Name of the switch to stop monitoring (string)
        callback: The callback function to remove
    
    Returns:
        bool: True if unsubscription successful, False otherwise
    """
    global switch_subscriptions
    
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
    diagnostics = []
    
    try:
        if "Switches" not in S.gdata or "Names" not in S.gdata["Switches"]:
            return diagnostics
        
        names = S.gdata["Switches"]["Names"]
        
        row=1
        col=1
        for idx, name_entry in enumerate(names):
            if idx >= len(switch_counts):
                break
            
            # Get switch name and sensitivity
            if isinstance(name_entry, list) and len(name_entry) >= 1:
                label = name_entry[0] if name_entry[0] else ""
                sensitivity = name_entry[1] if name_entry[1] else 60
            else:
                label = ""
                sensitivity = 0
            
            # Calculate health percentage (0-100%)
            # count = 0 → health = 100%, count >= sensitivity → health = 0%
            if sensitivity == 0:
                health = 100
            else:
                count = switch_counts[idx]
                health = max(0, min(100, 100 - (count * 100 // sensitivity))) 
            
            if label != "":
                diagnostics.append({
                    "row": row,
                    "col": col,
                    "val": health,
                    "label": label
                })

            row=row+1
            if row>8:
                row=1
                col=col+1

        print("\n\n",diagnostics,"\n\n")    
    
    except Exception as e:
        log.log(f"SWITCHES: Error in get_diagnostics: {e}")
    
    return diagnostics





# Initialize and schedule polling
from phew.server import schedule
init()
schedule(poll_switches, 15000, 5000)  # Poll every 5 seconds



