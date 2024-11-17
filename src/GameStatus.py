#game status
import SharedState as S
from Shadow_Ram_Definitions import shadowRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
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
        if low_digit > 9:
            low_digit=0
        if high_digit > 9:
            high_digit=0
        number_int = number_int * 100 + high_digit * 10 + low_digit
    return number_int

#read machine score (0=player1, 3=player4)
def get_machine_score(index):   
    try:
        score=0
        if S.gdata["InPlayScores"]["Type"] != 0:
            score_start = S.gdata["InPlayScores"]["ScoreAdr"] + index * S.gdata["InPlayScores"]["BytesInScore"]           
            score_bytes = shadowRam[score_start:score_start + S.gdata["InPlayScores"]["BytesInScore"]]  
            score=BCD_to_Int(score_bytes)
        return score    
    except Exception as e:
            print(f"GSTAT: error in get_machine_score: {e}")
    return 0


#get the ball in play #
def get_ball_in_play():
    try:
        ball_in_play = S.gdata["BallInPlay"] 
        if ball_in_play["Type"] == 1:        
            ball_token = shadowRam[ball_in_play["Address"]]        
            ball_values = {
                ball_in_play["Ball1"]: 1,
                ball_in_play["Ball2"]: 2,
                ball_in_play["Ball3"]: 3,
                ball_in_play["Ball4"]: 4,
                ball_in_play["Ball5"]: 5
            }
            # return 0 if no match
            return ball_values.get(ball_token, 0)
    except Exception as e:
            print(f"GSTAT: error in get_ball_in_play: {e}")
    return 0



def report(request):
    global game_active, number_of_players, time_game_start, time_game_end
    report_data = {}
  
    try:               
        report_data["BallInPlay"] = get_ball_in_play()        
        report_data["Player1Score"] = get_machine_score(0)
        report_data["Player2Score"] = get_machine_score(1)
        report_data["Player3Score"] = get_machine_score(2)
        report_data["Player4Score"] = get_machine_score(3)

        #game time 
        if time_game_start is not None:
            if game_active:
                report_data["GameTime"] = (time.ticks_ms() - time_game_start) / 1000
            elif time_game_end > time_game_start:
                report_data["GameTime"] = (time_game_end - time_game_start) / 1000
            else:
                report_data["GameTime"] = 0
        else:
            report_data["GameTime"] = 0

        report_data["GameActive"] = game_active
          
    except Exception as e:
        print(f"GSTAT: Error in report generation: {e}")        

    # Return the collected report data as JSON
    print("GSTAT: Report Data:", json.dumps(report_data)) 
    return json.dumps(report_data)
        
     
 
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
        if get_ball_in_play() !=0:
            time_game_start=time.ticks_ms()            
            game_active=True
            print("GSTAT: start game @ time=",time_game_start)
            poll_state=1
            
    elif poll_state==1:        
         if get_ball_in_play() == 0:
            time_game_end=time.ticks_ms()
            print("GSTAT: end gaem @ time=",time_game_end)
            game_active=False  
            poll_state=2

    else:
        poll_state=0

if __name__ == "__main__":
    print(report("ok"))


