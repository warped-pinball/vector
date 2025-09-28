"""Stub backend routes that are only loaded for EM builds."""

from time import sleep, time

from ujson import dumps as json_dumps

from system_features import get_system_features

_calibration_games = []
_capture_counter = 0
_pending_capture_id = None


def _next_capture_id():
    global _capture_counter
    _capture_counter += 1
    return f"capture-{_capture_counter}"


def register_ap_routes(add_route):
    """AP mode specific routes for EM systems."""
    # No EM specific AP routes yet. This function exists to keep the
    # registration code simple and symmetrical.
    return


def register_app_routes(add_route):
    """Register EM specific application routes."""

    @add_route("/api/em/status")
    def em_status(request):
        features = get_system_features()
        score_reels = int(features.get("default_score_reels", 4))
        return {
            "score_reels": score_reels,
            "calibration_games": list(_calibration_games),
            "pending_capture_id": _pending_capture_id,
            "max_games": int(features.get("max_calibration_games", 4)),
        }

    @add_route("/api/em/calibration/start_capture", auth=True)
    def em_start_capture(request):
        global _pending_capture_id
        capture_id = _next_capture_id()
        _pending_capture_id = capture_id

        messages = [
            {"progress": 0, "message": "Preparing to capture", "status": "capturing"},
            {"progress": 25, "message": "Listening for score reel activity", "status": "capturing"},
            {"progress": 50, "message": "Recording pulses", "status": "capturing"},
            {"progress": 75, "message": "Wrapping up capture", "status": "capturing"},
            {
                "progress": 100,
                "message": "Capture complete. Enter the final reel scores.",
                "status": "awaiting_score",
            },
        ]

        def generator():
            for entry in messages:
                payload = entry.copy()
                payload["capture_id"] = capture_id
                yield json_dumps(payload) + "\n"
                sleep(1)

        return generator()

    @add_route("/api/em/calibration/save_game", auth=True)
    def em_save_game(request):
        global _pending_capture_id
        data = request.data
        capture_id = data.get("capture_id")
        scores = data.get("scores", [])

        if not capture_id:
            return {"error": "Missing capture identifier"}, 400

        features = get_system_features()
        max_games = int(features.get("max_calibration_games", 4))

        saved_at = int(time())
        entry = {
            "capture_id": capture_id,
            "scores": scores,
            "saved_at": saved_at,
        }

        _calibration_games.append(entry)
        while len(_calibration_games) > max_games:
            _calibration_games.pop(0)

        if _pending_capture_id == capture_id:
            _pending_capture_id = None

        return {
            "calibration_games": list(_calibration_games),
            "score_reels": int(features.get("default_score_reels", 4)),
        }

    @add_route("/api/em/calibration/start_learning", auth=True)
    def em_start_learning(request):
        return {
            "status": "started",
            "games_available": len(_calibration_games),
            "timestamp": int(time()),
        }
