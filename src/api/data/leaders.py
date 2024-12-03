def app_leaderBoardRead(request):
        leaders = load_leaders()
        response = json.dumps(leaders)
        return (response) 

def load_leaders():
        gc.collect()
        leaders = []
        try:
            for i in range(DataStore.memory_map["leaders"]["count"]):
                leaders.append(DataStore.read_record("leaders", i))
        except Exception as e:
            print(f"Error loading leaders: {e}")
            leaders = []
        return leaders