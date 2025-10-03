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
    import time

    # TODO actually record the game and report progress
    target = 10

    for i in range(target):
        yield {"progress": (i + 1) / target * 100}
        time.sleep(1)
    return {"status": "done"}


@add_route("/api/em/set_calibration_scores", auth=True)
def final_calibration_game_scores(request):
    scores = [request.data.get(f"player_{i}_score").strip() for i in range(1, 5)]
    # TODO set final scores on calibration game


@add_route("/api/em/start_learning_process", auth=False)  # TODO auth True
def start_learning_process(request):
    import time

    # TODO actually start the learning process and report progress
    target = 20

    for i in range(target):
        yield {"progress": (i + 1) / target * 100}
        time.sleep(1)
    return {"status": "done"}
