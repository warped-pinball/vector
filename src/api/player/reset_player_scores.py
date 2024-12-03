   
    # def app_set_IndPlayer(request):
    #     global IndividualActivePlayer
    #     global IndividualActivePlayerNum        
    #     try:
    #         body = request.data                        
    #         playa = body['player']
    #         #print("Set player - ", playa)            
    #         count = DataStore.memory_map["names"]["count"]
    #         found = False

    #         for i in range(count):
    #             record = DataStore.read_record("names", i)
    #             initials = record['initials']                                
    #             if initials == playa:
    #                 IndividualActivePlayer = initials
    #                 IndividualActivePlayerNum = i
    #                 found = True
    #                 break
    #         if not found:
    #             return json.dumps({"error": "Player not found"})            
    #         #print("index => ",IndividualActivePlayerNum)
    #         return ("ok")
        
    #     except Exception as e:
    #         print(f"Error setting player: {e}")
    #         return ("error")
    

def app_deleteIndScores(request):
        global IndividualActivePlayerNum    
        global PassWordFail
        credentials = DataStore.read_record("configuration",0)             
        body = request.data     
        pw = body["password"]
        if pw ==  credentials["Gpassword"]:
                DataStore.blankIndPlayerScores(IndividualActivePlayerNum)   
                PassWordFail=False          
                print("del done")   
                return("ok")      
        PassWordFail=True  
        print("pass word fail set")
        time.sleep(1.5)
        return ("fail")