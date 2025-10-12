vectorSystem = "wpc"
updatesURL = "http://software.warpedpinball.com/vector/wpc/latest.json"

# Firmware version for the WPC build
SystemVersion = "1.0.0"


# System specific scheduled tasks
def schedule_system_tasks():
    # Note: this function is duplicated in src/sys11/systemConfig.py
    import faults
    from GameStatus import poll_fast
    from phew.server import copy_to_fram, schedule
    from ScoreTrack import CheckForNewScores

    schedule(CheckForNewScores, 15000, 5000)
    schedule(poll_fast, 15000, 250)

    # only if there are no hardware faults
    if not faults.fault_is_raised(faults.ALL_HDWR):
        # copy ram values to fram every 0.1 seconds
        schedule(copy_to_fram, 0, 100)
