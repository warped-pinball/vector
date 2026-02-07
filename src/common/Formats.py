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

#FORMAT RUN call timer in mS
CALL_TIMER = 1200
#system 11 normal initials timeout ~ 40 seconds per player
#WPC normal initials timeout is = 60 seconds 
OVER_COUNTER = 60000//CALL_TIMER

# Handler state var values
HANDLER_INIT = 0
HANDLER_RUN = 1
HANDLER_CLOSE = 2

next_format = {}  #hold the next format id,name,options,etc - will get copied into S.active_format when GameActive is False

# Forward declaration - will be initialized at end of file after handler functions are defined
FORMAT_HANDLERS = []

player_scores=[0,0,0,0]
saved_high_scores = None 

mode_ball_in_play=0  #store to detect change during play
mode_player_up=0

MODE_ID_STANDARD = 0
MODE_ID_LIMBO = 1
MODE_ID_LOWBALL = 2
MODE_ID_GOLF = 3
MODE_ID_PRACTICE = 4
MODE_ID_HALF_LIFE = 5
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
        "Sort": "Reverse",
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
        "Sort": "Normal",
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
        "Sort": "Reverse",
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
    "HalfLife": {
        "Id": MODE_ID_HALF_LIFE,
        "Description": "Score decreases over time",
        "Options": {
            "ScoreDecay": {
                "Name": "Half Life percent per 2 seconds",
                "type": "NumberRange",
                "Range": {
                    "Low": 1,
                    "High": 20                   
                },
                "Value": 2
            },
            "GetPlayerID": {
                "Value": True
            }
        }    
    },
    "LongestBall": {
        "Id": MODE_ID_LONGESTBALL,
        "Sort": "Normal",
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
    Set the active game format by its name (key) in to "next_format"
    Loads format settings in layers: defaults → config → runtime options
    """
    global next_format

    # Get formats from game configuration - only formats included in S.gdata can be used
    game_formats_config = S.gdata.get("Formats", {})
    if format_name not in game_formats_config or format_name not in DEFAULT_FORMATS:
        return False

    # Merge defaults and config: game_formats_config takes priority over DEFAULT_FORMATS
    combined_format = _deep_merge(DEFAULT_FORMATS.get(format_name, {}), game_formats_config.get(format_name, {}))

    # Apply incoming options (highest priority) to the Options section
    if options and isinstance(options, dict):
        if "Options" not in combined_format:
            combined_format["Options"] = {}
        combined_format["Options"] = _deep_merge(combined_format["Options"], options)

    next_format = combined_format.copy()
    # Store the format name for reference
    next_format["Name"] = format_name

    log.log(f"FORMAT: next format {format_name} id = {next_format.get('Id', 0)}")
    #print("\nNEXT FORMAT ------------------------- ",next_format,"\n")

    return True


# ============================================================================
# Practice Mode Handlers
# ============================================================================
def practice_init():
    """Initialize practice mode"""
    print("FORMAT: Practice mode initializing")

def practice_run():
    """Run practice mode (keep at ball 1 in play)"""
    global next_format
    if next_format.get("Id", 0) != MODE_ID_PRACTICE:  # end on next ball drain
        DataMapper.write_ball_in_play(5)
        DataMapper.write_live_scores([1, 1, 1, 1])
    elif DataMapper.get_ball_in_play() > 1:
        DataMapper.write_ball_in_play(1)

    max_score = S.active_format.get("Options", {}).get("MaxScore", {}).get("Value", 0)
    if max_score > 0:
        scores = DataMapper.get_live_scores()
        for idx in range(4):
            if scores[idx] >= max_score:
                scores[idx] = max_score
                DataMapper.write_live_scores(scores)
                break

    return DataMapper.get_game_active() 


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

    ball_in_play = DataMapper.get_ball_in_play()

    #copy all players scores to lowball
    if ball_in_play > 0:
        lowball_scores[ball_in_play - 1] = DataMapper.get_live_scores(use_format=False)

    # Update player_scores with the lowest non-zero score for each player
    for player_idx in range(4):
        scores = [lowball_scores[ball][player_idx] for ball in range(5) if lowball_scores[ball][player_idx] > 0]
        player_scores[player_idx] = min(scores) if scores else 0

    print("FORMAT: lowball scores:",lowball_scores)

    #if the ball in play changes set all scores to 0    
    if ball_in_play != mode_ball_in_play and ball_in_play != 0:
        print("FORMAT: set live scores to zero")
        DataMapper.write_live_scores([0,0,0,0])
    mode_ball_in_play=ball_in_play

    return DataMapper.get_game_active()
   




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

    print("FORMAT: Golf Init, options:",S.active_format.get("Options", {}))

    # Subscribe to target hit event
    if switch_callback_setup is False:
        target_name = S.active_format.get("Options", {}).get("Target", {}).get("Value", "")
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
    players_in_game = DataMapper.get_players_in_game()
    player_scores = [1_000_000 if i < players_in_game else 0 for i in range(4)]


def golf_run():
    """Run golf mode during gameplay"""
    global golf_ball_in_play, golf_player_up, golf_player_complete, player_scores

    ball_in_play = DataMapper.get_ball_in_play()
    player_up = DataMapper.get_player_up()
    players_in_game = DataMapper.get_players_in_game()

    #new players join
    for player_idx in range(players_in_game):
        if player_scores[player_idx] == 0:
            player_scores[player_idx] = 1_000_000

    
    if ball_in_play != golf_ball_in_play or player_up != golf_player_up:
        #had a change in ball or player - update scores etc
        num_players = DataMapper.get_players_in_game()
        
        # Check if all players are complete
        all_complete = True
        for idx in range(num_players):
            if not golf_player_complete[idx]:
                if (player_scores[idx]<6_000_000):
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
                #so we have ball 2 for the player currently up, if they are not done score up
                if golf_player_complete[player_up-1]==False:
                    player_scores[player_up - 1]=player_scores[player_up - 1] + 1_000_000

            if (ball_in_play >2):
                DataMapper.write_ball_in_play(2)            

            golf_ball_in_play = ball_in_play
            golf_player_up = player_up
    
    #always re-write scores - 
    DataMapper.write_live_scores(player_scores)
    return DataMapper.get_game_active()

def golf_close():
    """Close golf mode and unsubscribe from target"""
    global switch_callback_setup
    target_name = S.active_format.get("Options", {}).get("Target", {}).get("Value", "")
    if target_name:
        Switches.unsubscribe(target_name, golf_hit_callback)
        switch_callback_setup = False
        log.log(f"FORMAT: Unsubscribed from target '{target_name}'")



def golf_hit_callback(switch_idx):
    """
    Callback when the golf target switch is hit.
    Increments the current player's score (number of balls used).
    """
    #safety in case of subscription problem
    if S.active_format.get("Id", 0) != MODE_ID_GOLF:
        return

    #print("FORMAT: Golf switch hit --------------------------------------------------------------------")
    try:
        player_up = DataMapper.get_player_up()       

        if DataMapper.get_ball_in_play()==1 or DataMapper.get_ball_in_play()==5:
            if  player_scores[player_up - 1]<=1_000_000 and player_scores[player_up - 1]>250_000 and golf_player_complete[player_up - 1] is True:
                #reduce score on first ball, from 1,000,000->750,000->500,00->250,000
                player_scores[player_up - 1] -= 250_000 
                   
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
    return DataMapper.get_game_active()




# ============================================================================
# Half Life Mode Handlers
# ============================================================================
score_half_life_percent = 2  # Default value, will be overridden from config
def half_life_init():
    """Initialize half life mode - pull scoreDecay value from config"""
    global score_half_life_percent, player_scores
    
    # Get the decay percentage from format options
    config_percent = S.active_format.get("Options", {}).get("ScoreDecay", {}).get("Value", 2)
    # Normalize to actual call rate: convert from "per 2000ms" to "per CALL_TIMER ms"
    # If CALL_TIMER=1200ms, we want (1200/2000) of the configured percent per call
    score_half_life_percent = max(2, (config_percent * CALL_TIMER) // 2000 )

    player_scores = [0, 0, 0, 0]
    print(f"FORMAT: Half Life initialized with {score_half_life_percent}%")

def half_life_run():
    """Half Life run handler - reduce scores by percentage if above 10000"""
    global player_scores

    current_scores = DataMapper.get_live_scores(use_format=False)
    
    if DataMapper.get_game_active() is True:
        player_up = DataMapper.get_player_up()-1
        if current_scores[player_up] > 10000:           
            decay_amount = (current_scores[player_up] * score_half_life_percent) // 100
            current_scores[player_up] -= decay_amount

            # Write the decayed scores back to shadow RAM and player_scores
            DataMapper.write_live_scores(current_scores)

    player_scores = current_scores
    return DataMapper.get_game_active()

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


HOLD_TIMER_COUNT = max(1, 4100//CALL_TIMER)
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
        longest_ball_scores[ball_in_play-1][player_up-1] += (CALL_TIMER//10)
        player_scores[player_up-1] = longest_ball_scores[ball_in_play-1][player_up-1]

    print("FORMAT: LongestBall scores:",longest_ball_scores)

    #if game is ending - put the best single ball times in 
    if DataMapper.get_game_active() is False:
        # Find the highest (best) score for each player across all balls
        for player_idx in range(4):
            scores = [longest_ball_scores[ball][player_idx] for ball in range(5)]
            player_scores[player_idx] = max(scores)
        return False
    
    return True
  

# ============================================================================
# Stub Mode Handlers
# ============================================================================
def empty_init():
    """Empty init handler"""
    pass

def empty_run():
    """Empty run handler"""
    return DataMapper.get_game_active()

def empty_close():
    """Empty close handler"""
    pass



# ============================================================================
# FORMATS Runner
# ============================================================================
game_state =0
GameEndCount =0
last_high_score_count =0
in_play_scores_hold = [["", 0], ["", 0], ["", 0], ["", 0]]

def formats_run():
    """
    periodic tasks related to game formats.   
        call rate CALL_TIMER milli-seconds
    """
    global next_format, game_state, GameEndCount, player_scores, saved_high_scores, last_high_score_count, in_play_scores_hold

    # Waiting to change format?
    active_id = S.active_format.get("Id", 0)
    next_id = next_format.get("Id", 0)
    
    if active_id != next_id:        
        if DataMapper.get_game_active() is False and game_state==0:                   
            S.active_format = next_format.copy()
            print("FORMAT: Engage the waiting format:",S.active_format.get("Id"))
            return                        
            
    if active_id == MODE_ID_STANDARD:
        return

    #print("FORMATS: state=",game_state)
 
    #waiting for game to start
    if game_state == 0:
        if DataMapper.get_game_active() is True:  #game started
            game_state=1
            #remove machine high scores?
            get_player_id = S.active_format.get("Options", {}).get("GetPlayerID", {}).get("Value", False)
            if get_player_id:
                # prep for intials capture on game
                saved_high_scores = DataMapper.read_high_scores()
                DataMapper.remove_machine_scores()             

            #Run init function at each game start
            handlers = FORMAT_HANDLERS[active_id]                
            try:
                handlers[HANDLER_INIT]()
            except Exception as e:
                log.log(f"FORMAT: Error running init format {active_id}: {e}")
    

    # Call handler during game, wait for game end
    elif game_state == 1:       
        print("FORMAT: game end check")     
        handlers = FORMAT_HANDLERS[active_id]       
        try:
            game_active = handlers[HANDLER_RUN]()
        except Exception as e:
            log.log(f"FORMAT: Error running format {active_id}: {e}")
            game_active = DataMapper.get_game_active()

        if game_active is False:              
            game_state = 2
            GameEndCount = OVER_COUNTER

             
    # Game over wait for initials
    elif game_state == 2:    
        get_player_id = S.active_format.get("Options", {}).get("GetPlayerID", {}).get("Value", False)
        if get_player_id:
            GameEndCount -= 1    #wait for intials   
            if DataMapper.get_game_active() is True:
                   game_state = 3  
                   log.log("FORMAT: game started while waiting for intials")
            else:
                in_play_scores_hold = DataMapper.read_in_play_scores()

        else:
            game_state = 3  
            print("FORMAT: Do not wait for intiials")

        if GameEndCount <= 0:    
            game_state = 3   # timeout           
        else:
            scores = DataMapper.read_high_scores()
            print("FORMAT: high score read:",scores)
            
            # Check high scores - handle both WPC (5 scores) and SYS11 (4 scores) formats
            high_score_count = 0
            for x in range(0, min(5, len(scores))):
                alpha_count = sum(1 for c in scores[x][0] if c.isalpha())
                if scores[x][1] > 100 and alpha_count > 2:  #score and three initials are in 
                    high_score_count += 1

            if high_score_count >= DataMapper.get_players_in_game():                
                game_state=3        
            elif last_high_score_count != high_score_count:
                GameEndCount = OVER_COUNTER # renew timeout for next player to enter intiials
                last_high_score_count=high_score_count

            #print(f"\nFORMAT: game over, high score count $$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$$  {high_score_count}")
          
           
         
    elif game_state == 3:  #wrap up
            # Get in-play scores (in player order) and high scores (sorted by score)
            in_play_scores = in_play_scores_hold #DataMapper.read_in_play_scores()  #these are recorded by machine , not neccissarily a format result
            high_scores = DataMapper.read_high_scores()
            
            print(" in play scores",in_play_scores)
            print(" high scores : ",high_scores)            

            # Match in-play scores with high score initials to preserve player order
            final_scores_by_player = DataMapper.match_in_play_with_high_score_initials(in_play_scores, high_scores)
            
            # Replace scores in final_scores_by_player with format-adjusted scores from player_scores
            for player_idx in range(len(final_scores_by_player)):
                if player_idx < len(player_scores):
                    final_scores_by_player[player_idx][1] = player_scores[player_idx]            

            # Build scores list
            #scores = []
            #for idx in range(4):                
            #    initials = final_scores_by_player[idx][0] if final_scores_by_player[idx][0] else ""
            #    score = player_scores[idx]              
            #    scores.append([initials, score])
            
            log.log(f"FORMAT: RESULTS: {{Id:{active_id}, Scores:{final_scores_by_player}}}")
            

            '''
            try:
                from origin import push_end_of_game
                # Format: [gameCounter, [initials, score], [initials, score], [initials, score], [initials, score]]
                game = [S.gameCounter, final_scores_by_player[0], final_scores_by_player[1], final_scores_by_player[2], final_scores_by_player[3]]
                push_end_of_game(game)
            except Exception as e:
                log.log(f"FORMATS: Error pushing end of game to origin: {e}")
            '''

            # Restore original high scores if they were saved
            if saved_high_scores is not None:
                DataMapper.write_high_scores(saved_high_scores)
                saved_high_scores = None

            game_state=0

    else:
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
    [practice_init, practice_run, empty_close],
    # 5: Half Life
    [half_life_init, half_life_run, empty_close],
    # 6: Longest Ball
    [longest_ball_init, longest_ball_run, empty_close]
]


def initialize():
    # Initialize SharedState attributes and global next_format
    global next_format
    S.active_format = {"Id": 0, "Options": {}}
    next_format = {"Id": 0, "Options": {}}
  
    # Schedule periodic format tasks
    from phew.server import schedule
    schedule(formats_run, 12000, CALL_TIMER)

