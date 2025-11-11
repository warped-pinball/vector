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
            update_leaderboard(score)
        if list == "tournament":
            update_tournament(score)

    # Update the machine's top scores
    place_machine_scores()


# Removes a scores from a list. If it's leaders, and an individual score exists, remove that too.
def remove_score_entry(initials, score, list="leaders"):
    from ScoreTrack import find_player_by_initials, place_machine_scores

    player_name, player_num = (None, None)
    if list == "leaders" or list == "individual":
        player_name, player_num = find_player_by_initials({"initials": initials})

    # if specifically removing from individual, remove from their specific data set.
    data_set = 0
    if list == "individual":
        data_set = int(player_num)

    # Look for record in top scores and wipe it
    list_scores = [DataStore.read_record(list, i, data_set) for i in range(DataStore.memory_map[list]["count"])]
    for entry in list_scores:
        if list == "leaders":
            if entry["initials"] == initials and entry["score"] == score:
                log.log(f"SCORE: Deleting from '{list}' {entry}")
                entry["full_name"] = ""
                entry["initials"] = ""
                entry["date"] = ""
                entry["score"] = 0
                break
        if list == "tournament":
            if entry["initials"] == initials and entry["score"] == score:
                log.log(f"SCORE: Deleting from '{list}' {entry}")
                entry["initials"] = ""
                entry["index"] = 0
                entry["score"] = 0
                entry["game"] = 0
                break
        if list == "individual":
            if entry["score"] == score:
                log.log(f"SCORE: Deleting from '{list}' {entry}")
                entry["date"] = ""
                entry["score"] = 0
                break

    # Sort and prune the list before saving again.
    list_scores.sort(key=lambda x: x["score"], reverse=True)
    count = DataStore.memory_map[list]["count"]
    list_scores = list_scores[:count]
    for i in range(count):
        DataStore.write_record(list, list_scores[i], i, data_set)

    # Extra checks for leaderboard deletes
    if list == "leaders":
        # if leaders board, also prune from individual player list, if the score exists there too.
        if not (not player_name or player_name in [" ", "@@@", "   ", ""]) and (0 <= player_num < DataStore.memory_map["individual"]["count"]):
            individual_scores = []
            count = DataStore.memory_map["individual"]["count"]
            # individual_scores = [DataStore.read_record("individual", i, player_num) for i in range(DataStore.memory_map["individual"]["count"])]
            for i in range(count):
                existing_individual_score = DataStore.read_record("individual", i, player_num)
                if existing_individual_score and existing_individual_score.get("score") == score:
                    # Delete
                    log.log(f"SCORE: Deleting from 'individual' {existing_individual_score}")
                    existing_individual_score["date"] = ""
                    existing_individual_score["score"] = 0
                individual_scores.append(existing_individual_score)

            individual_scores.sort(key=lambda x: x["score"], reverse=True)
            individual_scores = individual_scores[:count]
            for i in range(count):
                DataStore.write_record("individual", individual_scores[i], i, player_num)

        # If this was the leaders list, set top_scores global var and update machine scores.
        from ScoreTrack import top_scores

        top_scores = [DataStore.read_record(list, i, data_set) for i in range(DataStore.memory_map[list]["count"])]
        # Write the top 4 scores to machine memory again, so they don't re-sync to vector.
        place_machine_scores()

    return True
