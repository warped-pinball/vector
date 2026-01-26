# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
Game format mode management.

This module provides functions to retrieve and manage different game formats
(e.g., Standard, Practice, Golf, etc.) from game configuration files.
"""
import SharedState as S
import DataMapper
import Switches
from logger import logger_instance
log = logger_instance

# Handler state var values
HANDLER_INIT = 0
HANDLER_RUN = 1
HANDLER_CLOSE = 2

next_format_id = 0
next_format_options = {}

# Forward declaration - will be initialized at end of file after handler functions are defined
FORMAT_HANDLERS = []

player_scores=[0,0,0,0]
saved_high_scores = None 
mode_ball_in_play=0
mode_player_up=0

MODE_ID_STANDARD = 0
MODE_ID_LIMBO = 1
MODE_ID_LOWBALL = 2
MODE_ID_GOLF = 3
MODE_ID_PRACTICE = 4
MODE_ID_DECAY = 5
MODE_ID_LONGESTBALL = 6


"""
    Default format definitions
    formats idetified by NAME (Key)
    config file overrides defaults from all parameters
    -when selecting a format send in values that override defaults here and in json
"""
DEFAULT_FORMATS = {
    "Standard": {
        "Id": MODE_ID_STANDARD,
        "Description": "Classic pinball scoring - highest score wins",
    },
    "Limbo": {
        "Id": MODE_ID_LIMBO,
        "Description": "Score as low as possible",        
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }        
    },
    "LowBall": {
        "Id": MODE_ID_LOWBALL,
        "Description": "Only the lowest scoring ball counts",
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }       
    },
    "Golf": {
        "Id": MODE_ID_GOLF,
        "Description": "Hit a specific target in the least number of balls",
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }    
    },
    "Practice": {
        "Id": MODE_ID_PRACTICE,
        "Description": "Practice mode with unlimited balls and no score tracking",
        "Options":{
            "MaxScore": {
                "Name": "Score Cap",
                "Type": "fixed",
                "Value": 0  #zero for no max               
            },
            "GetPlayerID": {                
                "Type": "fixed",
                "Value": False
            }
        }    
    },
    "Decay": {
        "Id": MODE_ID_DECAY,
        "Description": "Score decreases over time",
        "Options": {
            "ScoreDecay": {
                "Name": "Decay percent per 2.5 seconds",
                "type": "NumberRange",
                "Range": {
                    "Low": 1,
                    "High": 20                   
                },
                "Value": 2
            }
        }    
    },
    "LongestBall": {
        "Id": MODE_ID_LONGESTBALL,
        "Description": "Longest single ball play time wins",
        "Options": {
            "GetPlayerID": {
                "Name": "Collect Player Initials",
                "Type": "fixed",
                "Value": True
            }
        }                  
    }
}


def get_available_formats():
    """
    Retrieve available game formats from the current game configuration,
    overlaying config data onto defaults.
    """
    game_formats_config = S.gdata.get("Formats", {})
    result_formats = {}

    for name, config in game_formats_config.items():
        base = DEFAULT_FORMATS.get(name, {})
        result_formats[name] = _deep_merge(base, config)

    return result_formats


def _deep_merge(base, overlay):
    """
    Deep merge two dictionaries, with overlay values taking precedence.
    """
    result = base.copy()
    
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
            
    return result



def set_active_format(format_name, options=None):
    """
    Set the active game format by its name (key) in to "next_active_format"
    Loads format settings in layers: defaults → config → runtime options
    """
    global next_format_id, next_format_options

    # Get formats from game configuration
    game_formats_config = S.gdata.get("Formats", {})
    if format_name not in game_formats_config and format_name not in DEFAULT_FORMATS:
        return False

    # Merge defaults and config
    combined_format = _deep_merge(DEFAULT_FORMATS.get(format_name, {}), game_formats_config.get(format_name, {}))
    next_format_id = combined_format.get("Id", 0)

    # Only keep keys in Options with a "Value" key
    next_format_options = {}
    opts = combined_format.get("Options", {})
    for key, opt in opts.items():
        if isinstance(opt, dict) and "Value" in opt:
            next_format_options[key] = {"Value": opt["Value"]}

    # Overlay runtime options
    if options:
        next_format_options = _deep_merge(next_format_options, options)

    log.log(f"FORMAT: active format id = {next_format_id}")
    return True


# ============================================================================
# Practice Mode Handlers
# ============================================================================
def practice_init():
    """Initialize practice mode"""
    print("FORMATS: Practice mode initializing")

def practice_run():
    """Run practice mode (keep at ball 1 in play)"""
    if next_format_id != MODE_ID_PRACTICE:  # end on next ball drain
        DataMapper.write_ball_in_play(5)
        DataMapper.write_live_scores([1, 1, 1, 1])
    elif DataMapper.get_ball_in_play() > 1:
        DataMapper.write_ball_in_play(1)

    max_score = S.format_options.get("MaxScore", {}).get("Value", 0)
    if max_score > 0:
        scores = DataMapper.get_live_scores()
        for idx in range(4):
            if scores[idx] >= max_score:
                scores[idx] = max_score
                DataMapper.write_live_scores(scores)
                break

def practice_close():
    """Close practice mode"""
    print("FORMATS: Practice mode closing")




# ============================================================================
# Low Ball Mode Handlers  (only low scoring ball counts)
# ============================================================================
lowball_scores = [[0 for _ in range(4)] for _ in range(5)]  #[ball][player]
def lowball_init():
    """Initialize lowball mode"""
    global mode_ball_in_play, mode_player_up,lowball_scores
    mode_ball_in_play=1
    mode_player_up=1
    # Initialize lowball_scores to all zeroes
    lowball_scores = [[0 for _ in range(4)] for _ in range(5)]

def lowball_run():
    global mode_ball_in_play, mode_player_up, player_scores, lowball_scores
    # Update player_scores with the lowest non-zero score for each player
    for player_idx in range(4):
        scores = [lowball_scores[ball][player_idx] for ball in range(5) if lowball_scores[ball][player_idx] > 0]
        player_scores[player_idx] = min(scores) if scores else 0

    #if the ball in play changes set all scores to 0
    ball_in_play = DataMapper.get_ball_in_play()
    if ball_in_play != mode_ball_in_play:
        DataMapper.write_live_scores([0,0,0,0])

    #copy all players scores to lowball
    if ball_in_play > 0:
        lowball_scores[ball_in_play - 1] = DataMapper.get_live_scores(use_format=False)

    mode_ball_in_play=ball_in_play

  



# ============================================================================
# Golf Mode Handlers
# ============================================================================
golf_ball_in_play = 0
golf_player_up = 0
golf_player_complete = [False, False, False, False]
switch_callback_setup = False

def golf_init():
    """Initialize golf mode, called at game start each time"""
    global player_scores, golf_ball_in_play, golf_player_up, golf_player_complete, switch_callback_setup

    # Subscribe to target hit event
    if switch_callback_setup is False:
        target_name = S.format_options.get("Target", {}).get("Value", "")
        if target_name:
            switch_callback_setup = Switches.subscribe(target_name, golf_hit_callback)
            if switch_callback_setup:
                log.log(f"FORMAT: golf Subscribed to target '{target_name}'")
            else:
                log.log(f"FORMAT: Failed to subscribe to target '{target_name}'")
        else:
            log.log("FORMAT: No target selected for Golf")
    
    # Reset player scores and state for new game
    golf_ball_in_play = 1
    golf_player_up = 1
    golf_player_complete = [False, False, False, False]
    player_scores = [1000, 1000, 1000, 1000]


def golf_run():
    """Run golf mode during gameplay"""
    global golf_ball_in_play, golf_player_up, golf_player_complete, player_scores
    
    ball_in_play = DataMapper.get_ball_in_play()
    player_up = DataMapper.get_player_up()
    
    if ball_in_play != golf_ball_in_play or player_up != golf_player_up:
        #had a change in ball or player - update scores etc
        num_players = DataMapper.get_players_in_game()
        
        # Check if all players are complete
        all_complete = True
        for idx in range(num_players):
            if not golf_player_complete[idx]:
                if (player_scores[idx]<5000):
                    all_complete = False
                break
        
        if all_complete:
            log.log("FORMAT: Golf game end")
            # End the game
            DataMapper.write_ball_in_play(5)

            for idx in range(DataMapper.get_players_in_game()):
                print(f"  Player {idx + 1}: {player_scores[idx]}")        
        
        else:
            if ball_in_play ==1:
                golf_player_up = player_up
            else:
                #so we have ball 2 for the player currently up, if they are not done score=score*2
                if golf_player_complete[player_up-1]==False:
                    player_scores[player_up - 1]=player_scores[player_up - 1] + 1000

            if (ball_in_play >2):
                DataMapper.write_ball_in_play(2)

            golf_ball_in_play = ball_in_play
            golf_player_up = player_up
    
    #always re-write scores - 
    DataMapper.write_live_scores(player_scores)

def golf_close():
    """Close golf mode and unsubscribe from target"""
    global switch_callback_setup
    target_name = S.format_options.get("Target", {}).get("Value", "")
    if target_name:
        Switches.unsubscribe(target_name, golf_hit_callback)
        switch_callback_setup = False
        log.log(f"FORMAT: Unsubscribed from target '{target_name}'")



def golf_hit_callback(switch_idx):
    """
    Callback when the golf target switch is hit.
    Increments the current player's score (number of balls used).
    """
    try:
        player_up = DataMapper.get_player_up()       
        
        #golf_ball_in_play ==1 and
        if DataMapper.get_ball_in_play() == 1:
            if  player_scores[player_up - 1]<=1000 and player_scores[player_up - 1]>250 and golf_player_complete[player_up - 1] is True:
                #reduce score on first ball, from 1000->500->250
                player_scores[player_up - 1]=player_scores[player_up - 1]//2
                   
        golf_player_complete[player_up - 1] = True  #player done!

        # Check if all players in game are complete
        num_players = DataMapper.get_players_in_game()
        all_complete = True
        for idx in range(num_players):
            if not golf_player_complete[idx]:
                all_complete = False
                break
        
        if all_complete:
            print("FORMAT: golf all players complete!")
            DataMapper.write_ball_in_play(5)

    except Exception as e:
        log.log(f"FORMAT: Golf error in golf_hit_callback: {e}")




# ============================================================================
# Limbo Mode Handlers
# ============================================================================
def limbo_run():
    global player_scores
    player_scores = DataMapper.get_live_scores(use_format=False)
    return




# ============================================================================
# Decay Mode Handlers
# ============================================================================
score_decay_percent = 2  # Default value, will be overridden from config
def decay_init():
    """Initialize decay mode - pull scoreDecay value from config"""
    global score_decay_percent, player_scores
    
    # Get the decay percentage from format options
    score_decay_percent = S.format_options.get("ScoreDecay", {}).get("Value", 2)
    player_scores = [0, 0, 0, 0]
    print(f"FORMAT: Decay initialized with {score_decay_percent}%")

def decay_run():
    """Decay run handler - reduce scores by percentage if above 10000"""
    global player_scores
    
    current_scores = DataMapper.get_live_scores(use_format=False)
    
    player_up = DataMapper.get_player_up()-1
    if current_scores[player_up] > 10000:           
        decay_amount = (current_scores[player_up] * score_decay_percent) // 100
        current_scores[player_up] -= decay_amount

    # Write the decayed scores back to shadow RAM and player_scores
    DataMapper.write_live_scores(current_scores)
    player_scores = current_scores


# ============================================================================
# Longest Ball Mode Handlers
# ============================================================================
flipper_up_counter = 0
score_static_counter = 0
longest_ball_scores = [[0 for _ in range(4)] for _ in range(5)]  # [ball][player]
player_game_scores = [0, 0, 0, 0]

def longest_ball_init():
    """longest ball play time init handler"""
    global flipper_up_counter, score_static_counter, longest_ball_scores, player_game_scores
    global player_scores
    flipper_up_counter = 0
    score_static_counter = 4
    longest_ball_scores = [[0 for _ in range(4)] for _ in range(5)]
    player_game_scores = [0, 0, 0, 0]
    player_scores = [0, 0, 0, 0]

def longest_ball_run():
    """longest play time ball"""
    global flipper_up_counter, score_static_counter, longest_ball_scores, player_game_scores
    global player_scores

    player_up = DataMapper.get_player_up()
    ball_in_play = DataMapper.get_ball_in_play()

    # flipper held?
    left,right = DataMapper.get_flipper_state()
    if left is True or right is True:
        flipper_up_counter +=1
    else:
        flipper_up_counter=0   

    # game score incrementing?
    score_now = DataMapper.get_live_scores(use_format=False)
    if score_now[player_up-1] == player_game_scores[player_up-1]:
        score_static_counter += 1
    else:
        score_static_counter = 0
    player_game_scores = score_now

    if flipper_up_counter<2 and score_static_counter<2:
        # award time
        longest_ball_scores[ball_in_play-1][player_up-1] += 250
        player_scores[player_up-1] = longest_ball_scores[ball_in_play-1][player_up-1]

    #if game is ending - put the best single ball times in 
    if DataMapper.get_game_active() is False:
        # Find the highest (best) score for each player across all balls
        for player_idx in range(4):
            scores = [longest_ball_scores[ball][player_idx] for ball in range(5)]
            player_scores[player_idx] = max(scores)
          
  

# ============================================================================
# Stub Mode Handlers
# ============================================================================
def empty_init():
    """Empty init handler"""
    pass

def empty_run():
    """Empty run handler"""
    pass

def empty_close():
    """Empty close handler"""
    pass







# ============================================================================
# FORMATS Runner
# ============================================================================
game_state =0
GameEndCount =0

def formats_run():
    """
    periodic tasks related to game formats.   
        call rate 5 seconds
    """
    global next_format_id, next_format_options, game_state,GameEndCount,player_scores,saved_high_scores

    #waiting to change format?
    if S.active_format != next_format_id:
        if DataMapper.get_game_active() is False and game_state==0:           
            S.active_format = next_format_id
            S.active_format_name = next((name for name, fmt in DEFAULT_FORMATS.items() if fmt.get("Id") == next_format_id), "Standard")
            S.format_options = next_format_options   
            log.log("FORMAT: engage waiting format")
            return                        
            
    if S.active_format == MODE_ID_STANDARD:
        return

    #waiting for game to start
    if game_state == 0:
        if DataMapper.get_game_active() is True:  #game started
            game_state=1
            #remove machine high scores?
            get_player_id = S.format_options.get("GetPlayerID", {}).get("Value", False)
            if get_player_id:
                # prep for intials capture on game
                saved_high_scores = DataMapper.read_high_scores()
                DataMapper.remove_machine_scores(grand_champ_mode="Max")             

            #Run init function at each game start
            handlers = FORMAT_HANDLERS[S.active_format]                
            try:
                handlers[HANDLER_INIT]()
            except Exception as e:
                log.log(f"FORMATS: Error running init format {S.active_format}: {e}")
    

    # Call handler during game, wait for game end
    elif game_state == 1:       
        print("FORMATS: game end check")     

        if DataMapper.get_game_active() is False:   
            DataMapper.write_live_scores(player_scores) 
            game_state = 2

        handlers = FORMAT_HANDLERS[S.active_format]       
        try:
            handlers[HANDLER_RUN]()
        except Exception as e:
            log.log(f"FORMATS: Error running format {S.active_format}: {e}")
       

    #game over wait for intiials
    elif game_state == 2:
        DataMapper.write_live_scores(player_scores) 
        get_player_id = S.format_options.get("GetPlayerID", {}).get("Value", False)
        if get_player_id:
            GameEndCount += 1    #wait for intials   
            if DataMapper.get_game_active() is True:
                   GameEndCount = 99  #if game starts - get out!
                   log.log("FORMATS: game started while waiting for intials")
        else:
            GameEndCount = 99    #dont wait for intials
            print("FORMATS: Do not wait for intiials")

        if GameEndCount > 50:
            game_state = 3  
            GameEndCount = 0
        else:
            scores = DataMapper.read_high_scores()
            high_score_count = 0
            high_score_count = sum(1 for x in range(1, 5) if scores[x][1] > 100)
            log.log(f"FORMAT: game over, high score count {high_score_count}")

            if high_score_count >= DataMapper.get_players_in_game():                
                game_state=3
         
    elif game_state == 3:  #wrap up
            print("\n\nFORMATS: Game all done - results are:")
            
            # Get final scores
            final_scores = DataMapper.read_high_scores()
            num_players = DataMapper.get_players_in_game()
            
            # Print results for each player
            for idx in range(num_players):
                player_num = idx + 1
                initials = final_scores[player_num][0] if final_scores[player_num][0] else "___"
                score = final_scores[player_num][1]
                print(f"  Player {player_num} ({initials}): {score:,}")            
            
            try:
                from origin import push_end_of_game
                # Format: [gameCounter, [initials, score], [initials, score], [initials, score], [initials, score]]
                game = [S.gameCounter, final_scores[1], final_scores[2], final_scores[3], final_scores[4]]
                push_end_of_game(game)
            except Exception as e:
                log.log(f"FORMATS: Error pushing end of game to origin: {e}")

            # Restore original high scores if they were saved
            if saved_high_scores is not None:
                DataMapper.write_high_scores(saved_high_scores)
                saved_high_scores = None

            game_state=0



# List of handler lists indexed by format ID
# Each format has [init_handler, run_handler, close_handler]
FORMAT_HANDLERS = [
    # 0: Standard
    [empty_init, empty_run, empty_close],
    # 1: Limbo
    [empty_init, limbo_run, empty_close],
    # 2: LowBall
    [lowball_init, lowball_run, empty_close],
    # 3: Golf
    [golf_init, golf_run, golf_close],
    # 4: Practice
    [practice_init, practice_run, practice_close],
    # 5: Decay
    [decay_init, decay_run, empty_close],
    # 6: Longest Ball
    [longest_ball_init, longest_ball_run, empty_close]
]


def intiialize():
    # Initialize SharedState attributes if they don't exist
    if not hasattr(S, 'active_format'):
        S.active_format = 0
    if not hasattr(S, 'format_options'):
        S.format_options = {}

    # Schedule periodic format tasks
    from phew.server import schedule
    schedule(formats_run, 15000, 2500)










def test():
    formats = get_available_formats()
    print("\n&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&&\n")
    for key, value in formats.items():
        print(f"{key}: {value}\n")

  
    p = {
        "Target": {
            "Name": "Switch or feature to hit",
            "Value": 56
        }
    }

    z={}

    print("**************************set format Decay = ", set_active_format("Decay", z), "\n\n")

    for attr in dir(S):
        if not attr.startswith("__"):
            print(f"{attr}: {getattr(S, attr)}")

    print("\n\n")

