server.add_route("/IndPlayers", handler = app_get_IndPlayers, methods = ["GET"])


#get list of indvidual players from names list...    
def app_get_IndPlayers(request):      
    gc.collect()
    players = []      
    try:        
        count = DataStore.memory_map["names"]["count"]            
        for i in range(count):
            record = DataStore.read_record("names", i)
            initials = record['initials'].replace('\x00', ' ').strip() if record['initials'] else ' '            
            players.append( initials )
    except:
        print(f"Error accessing DataStore: {e}")
        return ("error")      
    return json.dumps({"players":players})

# these two appear to do basically the same thing, the lower one filters out blanks


def app_loadPlayers(request):
    gc.collect()
    players = {}
    #alphanumeric_pattern = re.compile(r'^[a-zA-Z0-9\x00 ]*$')
    def is_valid_string(s):
        return all(c.isalnum() or c == ' ' for c in s)    
    try:        
        count = DataStore.memory_map["names"]["count"]
        # Iterate through the player records
        for i in range(count):
            record = DataStore.read_record("names", i)
            initials = record['initials'].replace('\x00', ' ').strip('\0')  #if record['initials'] else ' '
            full_name = record['full_name'].replace('\x00', ' ').strip('\0')   #if record['full_name'] else ' '               
            if initials or full_name: # ensure that the record is not empty
                players[str(i + 1)] = {"initials": initials, "name": full_name}         

    except Exception as e:
        print(f"Error accessing DataStore: {e}")
        return json.dumps({"error": str(e)})
    
    return json.dumps(players)