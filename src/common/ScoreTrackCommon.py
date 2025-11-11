"""
Score Track Common
    Score Track Logic that is the same between system versions
"""

import SPI_DataStore as DataStore
from logger import logger_instance as log


def bulk_import_scores(scores, list="leaders"):
    from ScoreTrack import place_machine_scores, update_leaderboard, update_tournament

    # Merge imported data into respective leaderboards using existing logic.
    for score in scores:
        if score["score"] == 0:
            continue
        if list == "leaders":
            # Use existing leaderboard function
            update_leaderboard(score)
            # Update the machine's top scores
            place_machine_scores()
        if list == "tournament":
            import SharedState as S

            # Force game counter from score.
            cached_game = S.gameCounter
            if "index" in score and score["index"] != 0:
                # Put this tournament score in the correct game.
                S.gameCounter = score["game"]
                # Remove the "game" key from the dict, so it will save as new.
                del score["game"]
                update_tournament(score)
            # Put game counter back to what it was
            S.gameCounter = cached_game


# Removes a scores from a list. If it's leaders, and an individual score exists, remove that too.
def remove_score_entry(initials, score, list="leaders"):
    log.log(f"SCORE: Looking for {initials} {score} in '{list}'")
    from ScoreTrack import find_player_by_initials

    player_name, player_num = (None, None)
    data_set = 0
    # if specifically removing from individual, remove from their specific data set.
    if list == "individual":
        player_name, player_num = find_player_by_initials({"initials": initials})
        if (not player_name or player_name in [" ", "@@@", "   ", ""]) or (0 > player_num) or (player_num > DataStore.memory_map["individual"]["count"]):
            # Player isn't in the list, no need to continue
            return
        data_set = int(player_num)

    # Look for record in top scores and wipe it
    count = DataStore.memory_map[list]["count"]
    list_scores = []  # [DataStore.read_record(list, i, data_set) for i in range(count)]
    for i in range(count):
        entry = DataStore.read_record(list, i, data_set)
        if list == "leaders":
            if entry["initials"] == initials and entry["score"] == score:
                log.log(f"SCORE: Deleting from '{list}' {entry}")
                entry["full_name"] = ""
                entry["initials"] = ""
                entry["date"] = ""
                entry["score"] = 0

        if list == "tournament":
            if entry["initials"] == initials and entry["score"] == score:
                log.log(f"SCORE: Deleting from '{list}' {entry}")
                entry["initials"] = ""
                # entry["index"] = 0
                entry["score"] = 0
                entry["game"] = 0

        if list == "individual":
            if entry["score"] == score:
                log.log(f"SCORE: Deleting from '{list}' {entry}")
                entry["date"] = ""
                entry["score"] = 0

        list_scores.append(entry)

    # Sort and prune the list before saving again.
    list_scores.sort(key=lambda x: x["score"], reverse=True)
    list_scores = list_scores[:count]
    next_index = None
    for i in range(count):
        if list == "tournament":
            # Re-index tournament scores as we write. Index 0 Holds the next index
            print(f"Writing '{list}' record... at ", i)
            list_scores[i]["index"] = i
            print(list_scores[i])
            print(data_set)
            next_index = i + 1

        DataStore.write_record(list, list_scores[i], i, data_set)

    # If next index was set, set it at the 0 slot (Only for tournament)
    if next_index != None:
        if next_index >= count:
            next_index = 0
        rec = DataStore.read_record(list, 0, data_set)
        rec["index"] = next_index
        DataStore.write_record(list, rec, 0, data_set)

    return
