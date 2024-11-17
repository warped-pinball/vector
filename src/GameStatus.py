#game status
import SharedState as S
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import json
import time

game_active=False
number_of_players=0
time_game_start = None
time_game_end = None

#BCD two digits per byte
def BCD_to_Int(number_BCD):
    number_int = 0
    for byte in number_BCD:
        high_digit = byte >> 4
        low_digit = byte & 0x0F
        number_int = number_int * 100 + high_digit * 10 + low_digit
    return number_int


#read machine score (0=player1, 3=player4)
def readMachineScore_9(index):
    if index not in (0, 1, 2, 3):
        return "SCORE: Invalid index", 0
    # only use in play scores for system9
    score_start = S.gdata["InPlayScores"]["ScoreAdr"] + index * 4            
    initials=""
    # Read score (BCD to integer conversion) - 0xf is zero...
    score_bytes = shadowRam[score_start:score_start + S.gdata["InPlayScores"]["BytesInScore"]]  
    score = 0
    for byte in score_bytes:
        high_digit = byte >> 4        
        low_digit = byte & 0x0F
        if low_digit > 9:
            low_digit=0
        if high_digit > 9:
            high_digit=0
        score = score * 100 + high_digit * 10 + low_digit
    return initials, score    





def report(request):
    global game_active, number_of_players, time_game_start, time_game_end
    report_data = {}

    try:
        # Check if game-specific information is valid
        if S.gdata.get("GameInfo", {}).get("GameName") == "Pinbot":           

            try:
                # Game-specific data collection
                report_data["Warnings"] = shadowRam[0xB3]
                report_data["PlayerUp"] = shadowRam[0xAD] + 1
                report_data["SolarValue"] = 100 * BCD_to_Int(shadowRam[0x620:0x622 + 1])
                report_data["EnergyValue"] = 100 * BCD_to_Int(shadowRam[0xDB:0xDC + 1])
                report_data["Message"] = " "
                report_data["BallInPlay"] = shadowRam[0x38] & 0x0F

                # Gather player scores
                player_score = []
                for i in range(4):
                    base_idx = 0x200 + (i * 4)
                    score = BCD_to_Int(shadowRam[base_idx:base_idx + 4])
                    player_score.append(score)                    

                report_data["PlayerScore"] = player_score

                # Calculate game time only for a single player
                if number_of_players == 1 and time_game_start is not None:
                    if game_active:
                        report_data["GameTime"] = (time.ticks_ms() - time_game_start) / 1000
                    elif time_game_end > time_game_start:
                        report_data["GameTime"] = (time_game_end - time_game_start) / 1000
                    else:
                        report_data["GameTime"] = 0
                else:
                    report_data["GameTime"] = 0

                report_data["GameActive"] = game_active

                # Update player count based on shadowRam value
                number_of_players = shadowRam[0xAC] + 1
                report_data["Players"] = number_of_players

            except (IndexError, TypeError) as e:
                print(f"Data processing error: {e}")
                return json.dumps({"error": "Data processing error"})

            # Return the collected report data as JSON
            return json.dumps(report_data)
        
        else:
            # If game is not Pinbot, return "none"
            return "none"

    except Exception as e:
        # Handle any unexpected exceptions and prevent the function from locking up
        print(f"Unexpected error: {e}")
        return json.dumps({"error": "Unexpected error"})



 
def initialize():
    global game_active, number_of_players
    game_active=False
    number_of_players=0


poll_state=0
def poll_fast():
    global game_active,number_of_players,time_game_start,time_game_end,poll_state

    if poll_state==0:    
        #watch for ball in play for game start
        game_active=False
        if shadowRam[0x38] in [0xF1,0xF2,0xF3,0xF4,0xF5]:
            time_game_start=time.ticks_ms()            
            game_active=True
            print("-----------------start game ",time_game_start)
            poll_state=1
            
    elif poll_state==1:        
        if shadowRam[0xA9] == 0x01  or (shadowRam[0x38] not in [0xF1,0xF2,0xF3,0xF4,0xF5]):
            time_game_end=time.ticks_ms()
            print("------------end game ",time_game_end)
            game_active=False  
            poll_state=2

    else:
        if shadowRam[0x38] not in [0xF1,0xF2,0xF3,0xF4,0xF5]:
            poll_state=0
            print("----------reset")


if __name__ == "__main__":
    print(report("ok"))


