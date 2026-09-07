from backend import add_route
import SharedState as S
import os

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
        log.log(f"EMCAL: check_files error: {e}")
        return {"exists": [False, False, False, False], "count": 0, "error": str(e)}


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
