from backend import add_route
import SharedState as S
import os
try:
    import ujson as json
except Exception:
    import json
import time


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


@add_route("/api/em/record_calibration_game", auth=True)
def record_calibration_game(request):
    # TODO actually record the game and report progress
    target = 10




    for i in range(target):
        yield json.dumps({"progress": (i + 1) / target * 100})
        time.sleep(1)
    return json.dumps({"status": "done"})


@add_route("/api/em/set_calibration_scores", auth=True)
def final_calibration_game_scores(request):
    # scores come in like: {'scores': [[1], [2], [3333]]}
    scores_in = (request.data or {}).get("scores", [])
    flat = []
    for item in scores_in:
        # take first value of each inner list/tuple, else 0
        if isinstance(item, (list, tuple)) and item:
            flat.append(int(item[0]))
        else:
            flat.append(int(item or 0))
        if len(flat) == 4:
            break
    while len(flat) < 4:
        flat.append(0)

    print("score save ))))))))))))))))))))))))) ",flat)

    # pass a simple 4-int tuple
    from ScoreTrack import add_actual_score_to_file
    add_actual_score_to_file(filename=None, actualScores=tuple(flat))

    return {"status": "ok", "scores": flat}
   



@add_route("/api/em/start_learning_process", auth=True)
def start_learning_process(request):
    # TODO actually start the learning process and report progress
    target = 20

    for i in range(target):
        yield json.dumps({"progress": int((i + 1) / target * 100)})
        time.sleep(1)
    return json.dumps({"status": "done"})


@add_route("/api/em/recorded_games_count")
def recorded_games_count(request):
    """Return how many calibration game files exist.
    Counts files named game_history*.txt in the root directory.
    """
    try:
        cnt = 0
        for name in os.listdir("/"):
            if name.startswith("game_history") and name.endswith(".txt"):
                cnt += 1

        print(" game count recorded game coutn  = = = = = ",cnt)

        return {"count": cnt}
    except Exception as e:
        print("recorded_games_count error:", e)
        return {"count": 0, "error": str(e)}


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
    print("------------------------status deleted files", deleted_files)
    return json.dumps({"status": "deleted"})




@add_route("/api/em/diagnostics")
def diagnostics(request):
    """
    Stream diagnostic data similar to get_logs_stream() but for game history files.
    Streams the contents of any existing files named:
        game_history1, game_history2, game_history3, game_history4
    (no extension, per request)
    Each file is preceded by a header line and separated by blank lines.
    """
    import os

    candidate_files = ["game_history1", "game_history2", "game_history3", "game_history4"]
    existing = []
    try:
        root_list = os.listdir("/")
    except Exception:
        root_list = []
    for name in candidate_files:
        if name in root_list:
            existing.append("/" + name)

    def _stream():
        if not existing:
            yield "No game_history* files found.\n"
            return

        yield "Vector Diagnostics - Game History Dump\n"
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
                        try:
                            yield chunk.decode("utf-8", "ignore")
                        except Exception:
                            # fallback hex representation if undecodable
                            yield chunk.hex() + "\n"
            except Exception as e:
                yield f"[ERROR reading {path}: {e}]\n"
            yield f"\n==== END {path} ====\n"

        yield "\n-- End of diagnostics stream --\n"

    # Return the generator so the framework streams it
    return _stream()
