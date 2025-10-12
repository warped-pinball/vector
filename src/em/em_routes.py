import os

import SharedState as S
from backend import add_route

try:
    import ujson as json
except Exception:
    import json

import time

from logger import logger_instance

log = logger_instance


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
        S.gdata["dummy_reels"] = 0

    from ScoreTrack import saveState

    saveState()  # store in fram
    return


@add_route("/api/em/get_config")
def get_em_config(request):
    config = {
        "name": S.gdata["gamename"],
        "players": int(S.gdata["players"]),
        "reels_per_player": int(S.gdata["digits"]),
        "dummy_reels": int(S.gdata["dummy_reels"]),
    }
    return config


@add_route("/api/em/record_calibration_game", auth=True)
def record_calibration_game(request):
    """
    Find the first game_history<N>.dat (1..4) file that does NOT exist.
    Set ScoreTrack.fileNumber = N (1..4). If all exist, return an error.
    No placeholder file is created here.
    """
    import ScoreTrack

    ScoreTrack.storeCalibrationGameProgress = 0

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

        while S.run_learning_game == True:
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
    # target = 20

    from ScoreTrack import learnModeProcessNow

    learnModeProcessNow()

    # for i in range(target):
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

        # print("SSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSSS: ",exists,sum(1 for x in exists if x) )
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
                    filepath = root.rstrip("/") + "/" + name
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
                        # try:
                        #    yield chunk.decode("utf-8", "ignore")
                        # except Exception:
                        # fallback hex representation if undecodable
                        yield chunk.hex() + "\n"
            except Exception as e:
                yield f"[ERROR reading {path}: {e}]\n"
            yield f"\n==== END {path} ====\n"

        yield "\n-- End of diagnostics stream --\n"

    # Return the generator so the framework streams it
    return _stream()
