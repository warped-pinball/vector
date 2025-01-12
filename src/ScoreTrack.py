# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0 
"""
Score Track
    V0.2 9/7/2024  period after initials handling
    V0.3 11/25/2024 game over fix for high speed
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

rtc = RTC()

top_scores = None

#read machine score (0=higest,3=lowest)
def readMachineScore(index):
    if index not in (0, 1, 2, 3):
        return "SCORE: Invalid index", 0

    # Calculate address offsets
    score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4        
    initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3    

    # Read initials
    initials_bytes = shadowRam[initial_start:initial_start + 3]
    if S.gdata["HighScores"]["Type"] in [1,2]:  #0x40=space, A-Z normal ASCII        
        initials_bytes = [0x20 if b == 0x40 else (b & 0x7F) for b in initials_bytes]
        initials = bytes(initials_bytes).decode('ascii')
    elif S.gdata["HighScores"]["Type"]==3:   #0=space,1='0',10='9', 11='A'
        processed_initials = bytearray(
            [0x20 if byte == 0 else byte + 0x36 for byte in initials_bytes]
        )
        try:
            initials = processed_initials.decode('ascii') 
        except:
            initials=""
    else:
        initials=""

    # Read score (BCD to integer conversion)
    score_bytes = shadowRam[score_start:score_start + S.gdata["HighScores"]["BytesInScore"]]  
    score = 0
    for byte in score_bytes:
        high_digit = byte >> 4
        low_digit = byte & 0x0F
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
    global top_scores
    print("SCORE: Place Machine Scores")

    if S.gdata["HighScores"]["Type"] == 1 or S.gdata["HighScores"]["Type"] == 3:

        for index in range(4):    
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4      
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3  
            try:
                scoreBCD = int_to_bcd(top_scores[index]['score'])
            except:
                print("score convert problem")
                scoreBCD = int_to_bcd(100)   

            for i in range(S.gdata["HighScores"]["BytesInScore"]):
                shadowRam[score_start + i] = scoreBCD[i]                      
            try:
                print("  top scores: ",top_scores[index])     
                if S.gdata["HighScores"]["Type"]==1:
                    shadowRam[initial_start]=ord(top_scores[index]["initials"][0])  
                    shadowRam[initial_start+1]=ord(top_scores[index]["initials"][1])
                    shadowRam[initial_start+2]=ord(top_scores[index]["initials"][2])
                elif S.gdata["HighScores"]["Type"]==3:  
                    shadowRam[initial_start]=ascii_to_type3(ord(top_scores[index]["initials"][0]))
                    shadowRam[initial_start+1]=ascii_to_type3(ord(top_scores[index]["initials"][1]))
                    shadowRam[initial_start+2]=ascii_to_type3(ord(top_scores[index]["initials"][2]))

            except:
                print("place machine scores eception")
                shadowRam[initial_start]=64
                shadowRam[initial_start+1]=64
                shadowRam[initial_start+2]=64
    
   
#remove machine scores so all players will enter initials at the end of active game
def removeMachineScores():
    if S.gdata["HighScores"]["Type"] == 1: 
        log.log("SCORE: Remove machine scores 1")
        for index in range(4):    
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3

            shadowRam[score_start+0]=0
            shadowRam[score_start+1]=0
            shadowRam[score_start+2]=(5-index)
            shadowRam[score_start+3]=0
            shadowRam[initial_start+0]=0x3F
            shadowRam[initial_start+1]=0x3F
            shadowRam[initial_start+2]=0x3F       
    elif S.gdata["HighScores"]["Type"] == 3: 
        log.log("SCORE: Remove machine scores 3")
        for index in range(4):    
            score_start = S.gdata["HighScores"]["ScoreAdr"] + index * 4
            initial_start = S.gdata["HighScores"]["InitialAdr"] + index * 3

            shadowRam[score_start+0]=0
            shadowRam[score_start+1]=0
            shadowRam[score_start+2]=(5-index)
            shadowRam[score_start+3]=0
            shadowRam[initial_start+0]=0x00
            shadowRam[initial_start+1]=0x00
            shadowRam[initial_start+2]=0x00       
     

#find players name from list of intials with names from storage
def find_player_by_initials(new_entry):    
    findInitials = new_entry['initials']
    count=DataStore.memory_map["names"]["count"]
    for index in range(count):
        rec=DataStore.read_record("names",index)
        if rec is not None:           
            if rec['initials'] == findInitials:        
                player_name = rec['full_name'].strip('\x00')
                return (player_name,index)
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
    print(" num scores = ",num_scores,playernum)
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

    #any scores in ram (might not ne in leaders struct after reset)            
    for i in range(4):
        initials, score = readMachineScore(i)                    
        if any(0x40 < ord(initial) <= 0x5A for initial in initials[:3]):        
            year, month, day, _, _, _, _, _ = rtc.datetime()
            new_score = {
                'initials': initials,
                'full_name': '    ',
                'score': score,
                'date': f"{month:02d}/{day:02d}/{year}",
                "game_count": SharedState.gameCounter
            }                    
            update_leaderboard(new_score)               



def CheckForNewScores(nState=[0]):
    enscorecap = DataStore.read_record("extras", 0)["other"]
    if bool(enscorecap) != True or S.gdata["HighScores"]["Type"]==0 :
        return

    if S.gdata["BallInPlay"]["Type"] in [0, 1]:
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
                #game started, clear out scores  -
                removeMachineScores()
                SharedState.gameCounter = (SharedState.gameCounter +1) % 100
                nState[0]=1
            
        elif nState[0]==1:
            print("SERV: game end check")            
            if shadowRam[BallInPlayAdr] not in (Ball1Value, Ball2Value, Ball3Value, Ball4Value, Ball5Value, 0xFF):
                #game over, get new scores
                nState[0]=0
                #print("   leader update")
                for i in range(4):
                    initials, score = readMachineScore(i)
                    print("SCORE: new score: ",initials,score)
                
                    #check for valid intials
                    if any(0x40 < ord(initial) <= 0x5A for initial in initials[:3]):
                        #print("name passed test")
                        year, month, day, _, _, _, _, _ = rtc.datetime()
                        new_score = {
                            'initials': initials,
                            'full_name': '    ',
                            'score': score,
                            'date': f"{month:02d}/{day:02d}/{year}",
                            "game_count": SharedState.gameCounter
                        }                    
                        update_leaderboard(new_score)               
                placeMachineScores()
