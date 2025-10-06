from backend import add_route


@add_route("/api/em/set_config", auth=True)
def em_config(request):
    config = {
        "name": request.data.get("name").strip(),
        "players": int(request.data.get("players").strip()),
        "reels_per_player": int(request.data.get("reels_per_player").strip()),
        "dummy_reels": int(request.data.get("dummy_reels").strip()),
    }
    # TODO store in fram


@add_route("/api/em/get_config")
def get_em_config(request):
    # TODO get from fram
    config = {
        "name": "Example EM Game",
        "players": 4,
        "reels_per_player": 3,
        "dummy_reels": 2,
    }
    return config


@add_route("/api/em/record_calibration_game", auth=True)
def record_calibration_game(request):
    import json
    import time

    # TODO actually record the game and report progress
    target = 10

    for i in range(target):
        yield json.dumps({"progress": (i + 1) / target * 100})
        time.sleep(1)
    return json.dumps({"status": "done"})


@add_route("/api/em/set_calibration_scores", auth=True)
def final_calibration_game_scores(request):
    # Expecting `scores` to be an array of arrays sent in request.data by the web UI
    scores = request.data.get("scores")
    # TODO: validate and store scores in persistent storage
    return {"status": "ok", "received": bool(scores)}


@add_route("/api/em/start_learning_process", auth=True)
def start_learning_process(request):
    import time

    # TODO actually start the learning process and report progress
    target = 20

    for i in range(target):
        yield {"progress": (i + 1) / target * 100}
        time.sleep(1)
    return {"status": "done"}


@add_route("/api/em/recorded_games_count")
def recorded_games_count(request):
    """Return how many calibration games have been recorded out of 4.

    For now return a random number between 0 and 4 while the real
    implementation is not provided.
    """
    import random

    return {"count": random.randint(0, 4), "total": 4}


@add_route("/api/em/delete_calibration_games", auth=True)
def delete_calibration_games(request):
    """Delete all stored calibration games. Stub implementation returns success."""
    # TODO: actually remove stored calibration games from persistent storage
    return {"status": "deleted"}
