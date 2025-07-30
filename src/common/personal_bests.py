from typing import Dict, List, Any


def compute_personal_bests(players: Dict[str, Dict[str, str]],
                           scores: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Return each player's best score sorted descending.

    Parameters
    ----------
    players : mapping of player id to info with 'initials' and 'full_name'
    scores : mapping of player id to list of score records with 'score' and 'date'
    """
    results: List[Dict[str, Any]] = []

    for pid, info in players.items():
        best_score = None
        best_date = ""
        for record in scores.get(pid, []):
            if best_score is None or record.get("score", 0) > best_score:
                best_score = record.get("score", 0)
                best_date = record.get("date", "")
        if best_score is not None and best_score > 0:
            row = {
                "id": int(pid),
                "score": best_score,
                "date": best_date,
                "initials": info.get("initials", ""),
                "full_name": info.get("full_name", ""),
            }
            results.append(row)

    results.sort(key=lambda x: x["score"], reverse=True)
    for i, row in enumerate(results):
        row["rank"] = i + 1
    return results
