   
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



def app_get_IndScores(request):
        # These were being set by app_set_IndPlayer in a seperate call to the API
        global IndividualActivePlayer
        global IndividualActivePlayerNum 
        gc.collect()
        scores = []
        name = DataStore.read_record("names",IndividualActivePlayerNum)['full_name'].strip('\0')
        try:                      
            numberOfScores = DataStore.memory_map["individual"]["count"]
            #print("num ",numberOfScores)
            for i in range(numberOfScores):
                record = DataStore.read_record("individual", i,IndividualActivePlayerNum)  
                score = record['score']
                date = record['date'].strip().replace('\x00', ' ')          
                #print(score,date)                  
                scores.append({
                    "score": score,
                    "full_name": name,
                    "date": date
                })                       
        except Exception as e:
            print("Error accessing DataStore:", str(e))
            return json.dumps({"error": str(e)}) 
        return json.dumps(scores)