    @server.route("/install_fault")
    def app_install_fault(request):
        if SharedState.installation_fault:
            return "fault"
        else:
            return "ok"