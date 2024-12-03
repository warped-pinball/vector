
@server.route("/setEnableScoreCapture",methods=['POST'])
def app_setEnableScoreCapture(request):    
    gc.collect()
    newstate = int(request.data['enableScoreCapture'])  
    info=DataStore.read_record("extras", 0)
    info["other"] = newstate
    DataStore.write_record("extras",info,0)
    print("result -> ",newstate)  
    return("ok")
