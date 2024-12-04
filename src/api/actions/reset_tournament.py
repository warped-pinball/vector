@server.route("/tournamentClear")
def app_tournamentClear(request):
    DataStore.blankStruct("tournament")
    SharedState.gameCounter=0
    return("ok")       