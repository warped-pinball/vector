from backend import add_route
import SharedState as S
import os

try:
    import ujson as json
except Exception:
    import json

import time

from logger import logger_instance
log = logger_instance

@add_route("/api/em/sensor_activity")
def sensor_activity(request):
    """Return sensor activity state for the admin sensitivity indicator.

    state: "off"   -> no channels active
           "green" -> exactly one channel active
           "red"   -> more than one channel active
    """
    age = time.ticks_diff(time.ticks_ms(), S.sensor_last_hit_ms)
    active = (age < 600)
    level = int(getattr(S, "sensor_activity_level", 0))
    if not active:
        state = "off"
    elif level <= 0:
        state = "off"
    elif level == 1:
        state = "green"
    else:
        state = "red"
    return {"active": active, "age_ms": age, "level": level, "state": state}


@add_route("/api/em/set_config", auth=True)
def em_config(request):
    # Coerce and validate incoming values. client may send numbers rather than strings
    name = request.data.get("name")
    if name is None:
        S.gdata["gamename"] = ""
    else:
        S.gdata["gamename"] = str(name).strip()

    try:
        S.gdata["players"] = int(request.data.get("players") or 0)
    except Exception:
        S.gdata["players"] = 1

    try:
        S.gdata["digits"] = int(request.data.get("reels_per_player") or 0)
    except Exception:
        S.gdata["digits"] = 1

    try:
        S.gdata["dummy_reels"] = int(request.data.get("dummy_reels") or 0)
    except Exception:        
        S.gdata["dummy_reels"] =  0

    from ScoreTrack import saveState
    saveState()   # store in fram
    return


@add_route("/api/em/get_config")
def get_em_config(request):   
    config = {
        "name": S.gdata["gamename"],
        "players": int(S.gdata["players"]),
        "reels_per_player": int(S.gdata["digits"]),
        "dummy_reels":  int(S.gdata["dummy_reels"]),
    }
    return config


@add_route("/api/em/get_sensitivity")
def get_sensitivity(request):
    """Return the global detection sensitivity (1–100)."""
    sensitivity = S.gdata.get("sensitivity", 50)
    print(f"EMSEN: get_sensitivity -> {sensitivity}")
    return {"sensitivity": int(sensitivity)}


@add_route("/api/em/set_sensitivity", auth=True)
def set_sensitivity(request):
    """Set global detection sensitivity (0–100) and apply sensor thresholds."""
    print(f"EMSEN: set_sensitivity raw request data: {request.data}")
    try:
        value = int(request.data.get("sensitivity", 50))
        value = max(0, min(100, value))
    except Exception:
        value = 50

    try:
        import sensorRead

        value, low_thres, high_thres = sensorRead.setSensitivityPercent(value)
        print(f"EMSEN: thresholds set low={low_thres} high={high_thres}")
    except Exception as e:
        print(f"EMSEN: threshold apply failed: {e}")
        S.gdata["sensitivity"] = value

    from ScoreTrack import saveState
    saveState()
    print(f"EMSEN: set_sensitivity saved -> {value}")
    log.log(f"EMSEN: sensitivity set to {value}")
    return {"status": "ok", "sensitivity": value}


@add_route("/api/em/recalibrate_sensors", auth=True)
def recalibrate_sensors(request):
    """Force sensor calibration and then re-apply current sensitivity percent."""
    print("EMSEN: recalibrate_sensors start")
    try:
        import sensorRead

        sensorRead.calibrate()
        sensitivity = int(S.gdata.get("sensitivity", 50))
        sensitivity, low_thres, high_thres = sensorRead.setSensitivityPercent(sensitivity)

        from ScoreTrack import saveState

        saveState()
        print(f"EMSEN: recalibrate complete low={low_thres} high={high_thres} sensitivity={sensitivity}")
        log.log(f"EMSEN: recalibrate complete low={low_thres} high={high_thres} sensitivity={sensitivity}")
        return {"status": "ok", "sensitivity": sensitivity, "low": low_thres, "high": high_thres}
    except Exception as e:
        print(f"EMSEN: recalibrate failed: {e}")
        log.log(f"EMSEN: recalibrate failed: {e}")
        return {"status": "error", "message": str(e)}, 500


_TIMING_ADJ_COUNT = 5
_TIMING_ADJ_DEFAULT = [8, 8, 8, 8, 8]
_TIMING_ADJ_MIN = 1
_TIMING_ADJ_SCORE_MAX = 10
_TIMING_ADJ_RESET_MAX = 15


@add_route("/api/em/get_timing_sensitivity")
def get_timing_sensitivity(request):
    """Return per-player timing sensitivity arrays (5 values each).
    Score values are 1–10. Reset values are 1–15.
    Keys: p1_score, p1_reset, p2_score, p2_reset.
    """
    def _get(key, value_max):
        v = list(S.gdata.get(key, _TIMING_ADJ_DEFAULT))
        if len(v) != _TIMING_ADJ_COUNT:
            v = _TIMING_ADJ_DEFAULT[:]
        out = []
        for item in v:
            try:
                num = int(item)
            except Exception:
                num = _TIMING_ADJ_DEFAULT[len(out)]
            num = max(_TIMING_ADJ_MIN, min(value_max, num))
            out.append(num)
        return out

    p1_score = _get("timing_p1_score", _TIMING_ADJ_SCORE_MAX)
    p1_reset = _get("timing_p1_reset", _TIMING_ADJ_RESET_MAX)
    p2_score = _get("timing_p2_score", _TIMING_ADJ_SCORE_MAX)
    p2_reset = _get("timing_p2_reset", _TIMING_ADJ_RESET_MAX)
    print(f"EMSEN: get_timing_sensitivity -> p1_score={p1_score} p1_reset={p1_reset} p2_score={p2_score} p2_reset={p2_reset}")
    return {"p1_score": p1_score, "p1_reset": p1_reset, "p2_score": p2_score, "p2_reset": p2_reset}


@add_route("/api/em/set_timing_sensitivity", auth=True)
def set_timing_sensitivity(request):
    """Set per-player timing sensitivity arrays (5 values each).
    Score values are 1–10. Reset values are 1–15.
    Expects: p1_score, p1_reset, p2_score, p2_reset.
    """
    print(f"EMSEN: set_timing_sensitivity raw request data: {request.data}")

    def _coerce(raw, value_max):
        try:
            out = [max(_TIMING_ADJ_MIN, min(value_max, int(v))) for v in raw]
        except Exception:
            out = _TIMING_ADJ_DEFAULT[:]
        if len(out) != _TIMING_ADJ_COUNT:
            out = _TIMING_ADJ_DEFAULT[:]
        return out

    d = request.data or {}
    p1_score = _coerce(d.get("p1_score", _TIMING_ADJ_DEFAULT), _TIMING_ADJ_SCORE_MAX)
    p1_reset = _coerce(d.get("p1_reset", _TIMING_ADJ_DEFAULT), _TIMING_ADJ_RESET_MAX)
    p2_score = _coerce(d.get("p2_score", _TIMING_ADJ_DEFAULT), _TIMING_ADJ_SCORE_MAX)
    p2_reset = _coerce(d.get("p2_reset", _TIMING_ADJ_DEFAULT), _TIMING_ADJ_RESET_MAX)

    S.gdata["timing_p1_score"] = p1_score
    S.gdata["timing_p1_reset"] = p1_reset
    S.gdata["timing_p2_score"] = p2_score
    S.gdata["timing_p2_reset"] = p2_reset

    from ScoreTrack import saveState
    saveState()
    print(f"EMSEN: set_timing_sensitivity saved -> p1_score={p1_score} p1_reset={p1_reset} p2_score={p2_score} p2_reset={p2_reset}")
    log.log(f"EMSEN: timing p1_score={p1_score} p1_reset={p1_reset} p2_score={p2_score} p2_reset={p2_reset}")
    return {"status": "ok", "p1_score": p1_score, "p1_reset": p1_reset, "p2_score": p2_score, "p2_reset": p2_reset}


@add_route("/api/em/record_calibration_game", auth=True)
def record_calibration_game(request):
    """
    Find the first game_history<N>.dat (1..4) file that does NOT exist.
    Set ScoreTrack.fileNumber = N (1..4). If all exist, return an error.
    No placeholder file is created here.
    """
    import ScoreTrack
    ScoreTrack.storeCalibrationGameProgress=0

    try:
        # use check_files() to see which slots exist
        info = check_files()
        exists = info.get("exists", [False, False, False, False])

        for idx, present in enumerate(exists, start=1):
            if not present:
                ScoreTrack.fileNumber = idx
                break

        log.log(f"EMCAL: store file num: {idx}")
        S.run_learning_game = True

        while (S.run_learning_game == True):
            print("&", end="")
            yield json.dumps({"progress": ScoreTrack.storeCalibrationGameProgress})
            time.sleep(0.5)
       
        return {"status": "ok"}

    except Exception as e:
        S.run_learning_game = False
        return {"status": "error", "error": str(e)}, 500


@add_route("/api/em/set_calibration_scores", auth=True)
def final_calibration_game_scores(request):
    scores_in = (request.data or {}).get("scores", [])
    log.log(f"EMCAL: raw score entry {scores_in}")

    def to_int(v):
        try:
            return int(v)
        except Exception:
            return 0

    # compose each inner list of digits into an integer
    composed = []
    for series in scores_in:
        n = 0
        if isinstance(series, (list, tuple)):
            for d in series:
                n = n * 10 + to_int(d)
        else:
            n = to_int(series)
        composed.append(n)
        if len(composed) == 4:
            break

    # pad to 4 scores
    while len(composed) < 4:
        composed.append(0)

    log.log(f"EMCAL: score save {composed}")
    from ScoreTrack import add_actual_score_to_file
    add_actual_score_to_file(filename=None, actualScores=tuple(composed))

    return {"status": "ok", "scores": composed}
   



@add_route("/api/em/start_learning_process", auth=True)
def start_learning_process(request):
    # TODO actually start the learning process and report progress
    #target = 20

    from ScoreTrack import learnModeProcessNow
    learnModeProcessNow()

    #for i in range(target):
    #    yield json.dumps({"progress": int((i + 1) / target * 100)})
    #    time.sleep(1)
    return json.dumps({"status": "done"})





@add_route("/api/em/recorded_games_count")
def recorded_games_count(request):
    return check_files()

def check_files():   
    """
    Check for game_history1.dat .. game_history4.dat return boolean array of their existence.
    """ 
    try:
        try:
            names = set(os.listdir("/"))
        except Exception:
            names = set(os.listdir())

        exists = []
        for idx in range(1, 5):
            fname = f"game_history{idx}.dat"
            exists.append(fname in names)

        #print("SSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSS: ",exists,sum(1 for x in exists if x) )
        return {"exists": exists, "count": sum(1 for x in exists if x)}
    
    except Exception as e:
        log.log(f"EMCAL: recorded_games_count error: {e}")
        return {"exists": [False, False, False, False], "count": 0, "error": str(e)}


@add_route("/api/em/delete_calibration_games", auth=True)
def delete_calibration_games(request):
    print("CAL GAMes DEL ----------------------------")
    """Delete all stored calibration games. Deletes files starting with 'game_history' in root directory."""
    deleted_files = []
    roots = ["/"]
    for root in roots:
        try:
            for name in os.listdir(root):
                if name.startswith("game_history"):
                    filepath = (root.rstrip("/") + "/" + name)
                    try:
                        os.remove(filepath)
                        deleted_files.append(filepath)
                    except Exception:
                        pass
        except Exception:
            pass    
    log.log("EMCAL: delete calibration files")
    return json.dumps({"status": "deleted"})




@add_route("/api/em/diagnostics")
def diagnostics(request):
    """
    Stream diagnostic data - game history files.   
    """
    import os

    candidate_files = ["game_history1.dat", "game_history2.dat", "game_history3.dat", "game_history4.dat"]       
    info = check_files()
    exists = info.get("exists", [False, False, False, False])
    existing = ["/" + name for name, present in zip(candidate_files, exists) if present]

    def _stream():
        if not existing:
            yield "No game_history* files found.\n"
            return

        yield "Vector EM Diagnostics - Game History Dump\n"
        yield "Files: " + ", ".join(existing) + "\n"
        yield "----------------------------------------\n"

        for path in existing:
            yield f"\n==== BEGIN {path} ====\n"
            try:
                with open(path, "rb") as f:
                    while True:
                        chunk = f.read(256)
                        if not chunk:
                            break
                        # convert to str safely
                        #try:
                        #    yield chunk.decode("utf-8", "ignore")
                        #except Exception:
                        # fallback hex representation if undecodable
                        yield chunk.hex() + "\n"
            except Exception as e:
                yield f"[ERROR reading {path}: {e}]\n"
            yield f"\n==== END {path} ====\n"

        yield "\n-- End of diagnostics stream --\n"

    # Return the generator so the framework streams it
    return _stream()
