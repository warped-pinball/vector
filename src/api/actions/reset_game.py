def app_resetGame(request):              
    reset_control.reset()
    time.sleep(2)
    reset_control.release(True)         
    server.reset_bootup_counters()
    return("ok")