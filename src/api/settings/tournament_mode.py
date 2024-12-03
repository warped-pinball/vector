 @server.route("/tournamentMode")
    def app_tournamentmode(request):
        SharedState.tournamentModeOn=1
        return ("ok")


    @server.route("/leaderMode")
    def app_leaderMode(request):
        SharedState.tournamentModeOn=0
        return("ok")
