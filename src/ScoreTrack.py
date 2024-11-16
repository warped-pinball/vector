# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
Score Track
    V0.2 9/7/2024  period after initials handling
    New for System 9 machines  (Nov. 2024)
"""

import json
import os
from Shadow_Ram_Definitions import shadowRam,writeCountRam,SRAM_DATA_LENGTH,SRAM_DATA_BASE,SRAM_COUNT_BASE
import SharedState
from machine import RTC
import SPI_DataStore as DataStore
import SharedState as S
from logger import logger_instance
log = logger_instance
import displayMessage

rtc = RTC()
top_scores = None

#hold the last four (plus two older records) games worth of scores.  game counter and 4 scores plus intiials--
recent_scores = [
    [0, ("a", 50), ("b", 550), ("c", 5560), ("d", 7560)], 
    [0, ("e", 10), ("", 0), ("", 0), ("", 0)], 
    [0, ("", 54360), ("", 6540), ("", 6450), ("", 60)], 
    [0, ("", 0), ("CRM", 7560), ("", 0), ("", 0)],  
    [0, ("", 0), ("", 0), ("", 0), ("", 0)],
    [0, ("", 0), ("", 0), ("", 0), ("", 0)]
]

def get_claim_score_list():
    return recent_scores[:4]


def claim_scores(scores):
    print("Incoming new score claims ->", scores)

    for claim in scores:  # Iterate over each game in the incoming claims
        claim_game_counter = claim[0]
        claim_scores_and_initials = claim[1:]

        for recent_game in recent_scores:  # Iterate over each game in recent_scores
            recent_game_counter = recent_game[0]
            recent_scores_and_initials = recent_game[1:]

            # Match game counters
            if claim_game_counter == recent_game_counter:
                # Check each score
                for i, (claim_initials, claim_score) in enumerate(claim_scores_and_initials):
                    recent_initials, recent_score = recent_scores_and_initials[i]

                    # Match scores
                    if claim_score == recent_score:
                        if claim_initials:  # If initials are provided in the claim
                            recent_scores[recent_scores.index(recent_game)][i + 1] = (
                                claim_initials,
                                recent_score,
                            )
                            print(f"Updated initials for score {claim_score} -> {claim_initials}")

                            # Call record_new_score with the updated game record
                            #record_new_score(recent_scores[recent_scores.index(recent_game)])
    return "ok"


#read machine score (0=higest,3=lowest)
def readMachineScore(index):
    if index not in (0, 1, 2, 3):
        return "SCORE: Invalid index", 0

    # onlyu using in play scores for system9
    score_start = S.gdata["InPlayScores"]["ScoreAdr"] + index * 4        
    #initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3    

    # Read initials
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
  
#convert integer to 8 digit BCD number like stored in game for high scores
def int_to_bcd(number):
    # Ensure the number is within the acceptable range
    if not (0 <= number <= 99999999):
        raise ValueError("SCORE: Number out of range")
    
    #pad with zeros to ensure it has 7 digits
    num_str = f"{number:08d}"    
    bcd_bytes = bytearray(4)
    
    # Fill byte array
    bcd_bytes[0] = (int(num_str[0]) << 4) + int(num_str[1]) # Millions
    bcd_bytes[1] = (int(num_str[2]) << 4) + int(num_str[3]) # Hundred-th & ten-th
    bcd_bytes[2] = (int(num_str[4]) << 4) + int(num_str[5]) # Thousands & hundreds
    bcd_bytes[3] = (int(num_str[6]) << 4) + int(num_str[7]) # Tens & ones
    return bcd_bytes

def ascii_to_type3(c):
    if c==0x20 or c<0x0B or c>0x90: return 0
    return (c-0x36)  #char
  
#write four highest scores from storage to machine memory    
def placeMachineScores():
   return 0
    
   
#remove machine scores - replace with high #s
def removeMachineScores():
    if S.gdata["HighScores"]["Type"] == 9: 
        log.log("SCORE: Remove machine high scores")
        for index in range(4):    
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * S.gdata["HighScores"]["BytesInScore"]           
            shadowRam[score_start+0]=0xF9
            shadowRam[score_start+1]=0x99
            shadowRam[score_start+2]=0x99
            shadowRam[score_start+3]=0x99    
  
     

#find players name from list of intials with names from storage
def find_player_by_initials(new_entry):       
    return (' ',-1)


#update a players individual high score     
def Update_individualScore(new_entry):
    initials = new_entry['initials']        
    playername,playernum=find_player_by_initials(new_entry) 

    if not playername or playername in [' ', '@@@','   ']:
        print("SCORE: No indiv player ",initials)
        return False

    if not (0 <= playernum < DataStore.memory_map["individual"]["count"]):
        print("SCORE: Player out of range")
        return False

    new_entry['full_name'] = playername

    # Load existing scores
    scores=[]
    num_scores=DataStore.memory_map["individual"]["count"]
    print(" num sores = ",num_scores,playernum)
    for i in range(num_scores): 
        scores.append(DataStore.read_record("individual", i, playernum))     

    scores.append(new_entry)            
    scores.sort(key=lambda x: x['score'], reverse=True)            
    scores = scores[:20]        
    #for score in scores:
    #    print(score)

    # Save the updated scores
    for i in range(num_scores): 
        DataStore.write_record("individual", scores[i], i, playernum) 
        
    print(f"Updated scores for {initials}")
    return True
  

# in tournament mode
def update_tournamentboard(new_entry):
    count=DataStore.memory_map["tournament"]["count"]
    rec=DataStore.read_record("tournament",0)
    nextIndex=rec["index"]
   
    new_entry["game"]=SharedState.gameCounter 
    new_entry["index"]=nextIndex
    DataStore.write_record("tournament",new_entry,nextIndex)
    #print("tourn ",new_entry)

    nextIndex+=1
    if nextIndex >= count: nextIndex=0
    rec=DataStore.read_record("tournament",0)
    rec["index"]=nextIndex
    DataStore.write_record("tournament",rec,0)
    return 


#this function is called by server when an end of game is detected
#  it is called once for each valid inital/score combo (up to 4)
#
#add a score to leaderboards
def update_leaderboard(new_entry):        
    global top_scores    

    #check for bogus intiials 
    if new_entry['initials'] == "@@@" or new_entry['initials'] == "   ":
        return False

    print("SCORE: Update Leader Board: ",new_entry)
    
    #if tournamnet mode do only tournamnet save - - - 
    if SharedState.tournamentModeOn == 1:
        print("SCORE: Tournament Mode")
        update_tournamentboard(new_entry)
        return 
   
    Update_individualScore(new_entry)
   
    #add player name to new_entry if there is an initals match    
    new_entry['full_name'],ind=find_player_by_initials(new_entry)
    if new_entry['full_name'] is None:
        new_entry['full_name'] =" "
   
    #load scores 
    top_scores=[]
    count=DataStore.memory_map["leaders"]["count"]
    for i in range(count): 
        top_scores.append(DataStore.read_record("leaders", i))    

    # Check if the new_entry already exists in the top_scores
    for entry in top_scores:
        if entry['initials'] == new_entry['initials'] and entry['score'] == new_entry['score']:
            return False  # Entry already exists, do not add it

    # Check if the new score is higher than the lowest in the list or if the list is not full
    top_scores.append(new_entry) 
    top_scores.sort(key=lambda x: x['score'], reverse=True)
    #top 20
    top_scores = top_scores[:count]
    
    for i in range(count):         
        DataStore.write_record("leaders", top_scores[i], i)

    return True


#power up init for leader board
def initialize_leaderboard():
    global top_scores 
    if top_scores is None:
        top_scores = []
    print("SCORE: Init leader board")

    #init gameCounter, find highest # in tournament board
    n = 0
    for i in range(DataStore.memory_map["tournament"]["count"]):
        try:
            game_value = DataStore.read_record("tournament", i)["game"]
            n = max(game_value, n)
        except (KeyError, TypeError):
            print(f"Error reading game value at index {i}")
            continue
    S.gameCounter = n

    top_scores=[]
    count=DataStore.memory_map["leaders"]["count"]
    for i in range(count): 
        top_scores.append(DataStore.read_record("leaders", i))    

    #make sure we have 4 entries
    while len(top_scores) < 4:
        fake_entry = {
            'initials': 'ZZZ',
            'full_name': ' ',
            'score': 100,
            'date': '04/17/2024'
        }
        top_scores.append(fake_entry)      


# this is the function called by server
def CheckForNewScores(nState=[0]):

    enscorecap = DataStore.read_record("extras", 0)["other"]
    if bool(enscorecap) != True or S.gdata["HighScores"]["Type"]==0 :
        return

    if S.gdata["BallInPlay"]["Type"] == 1:
        BallInPlayAdr = S.gdata["BallInPlay"]["Address"] 
        Ball1Value = S.gdata["BallInPlay"]["Ball1"]
        Ball2Value = S.gdata["BallInPlay"]["Ball2"]
        Ball3Value = S.gdata["BallInPlay"]["Ball3"]
        Ball4Value = S.gdata["BallInPlay"]["Ball4"]
        Ball5Value = S.gdata["BallInPlay"]["Ball5"]
        
        #discover new scores
        if nState[0]==0:  #wait for a game to start
            print("SERV: game start check")
            if shadowRam[BallInPlayAdr] in (Ball1Value,Ball2Value,Ball3Value,Ball4Value,Ball5Value):
                #game started, clear out IP address put in big high scores
                removeMachineScores()
                SharedState.gameCounter = (SharedState.gameCounter +1) % 100
                nState[0]=1
            
        elif nState[0]==1:
            print("SERV: game end check")

            #collect scores in progress...
            for i in range(4):
                print(readMachineScore(i))
                    
            if shadowRam[BallInPlayAdr] not in (Ball1Value, Ball2Value, Ball3Value, Ball4Value, Ball5Value):
                #game over, get new scores
                nState[0]=0                
                for i in range(4): 
                    initials, score = readMachineScore(i)
                    print("SCORE: new score: ",initials,score)       

                #place scores in temp list for player to claim...
                recent_scores[5] = recent_scores[4]  
                recent_scores[4] = recent_scores[3]  
                recent_scores[3] = recent_scores[2]  
                recent_scores[2] = recent_scores[1]  
                recent_scores[1] = recent_scores[0]  
                recent_scores[0]=[SharedState.gameCounter,readMachineScore(0),readMachineScore(1),readMachineScore(2),readMachineScore(3)]
                print(recent_scores)

                #put ip address back up on displays
                displayMessage.refresh_9()


