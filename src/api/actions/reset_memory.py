    def app_resetMemory(request):
        try:
            reset_control.reset()
            time.sleep(2)
            blank_ram()
            time.sleep(1)
            reset_control.release(True)
            server.reset_bootup_counters()
            return "ok"
        except Exception as e:
            print(f"Error in app_resetMemory: {e}")
            return "Error", 500