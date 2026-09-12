import SPI_DataStore as datastore
import ScoreTrack

def read_highscores():
    # Read the configuration record from storage
    #scores = datastore.read_record("leaders")

    count = datastore.memory_map["leaders"]["count"]
    scores = [datastore.read_record("leaders", i) for i in range(count)]

    return scores

def write_highscores(scores):
    # Write the updated scores
    count = datastore.memory_map["leaders"]["count"]
    scores = scores[:count]
    for i in range(count):
        datastore.write_record("leaders", scores[i], i)




def edit_scores(scores):  
    print("\nEnter position # to edit (1-20, or type '0' to end):")
    
    # Ensure we have all 20 positions
    #while len(scores) < 20:
    #    scores = scores + [{"initials": "AAA", "score": 0}]

    while True:
        try:
            position = int(input("Position number: "))
            if position == 0:
                break
                
            if position < 1 or position > 20:
                print("Please enter a number between 1 and 20")
                continue
                
            # Adjust for 0-based indexing
            idx = position - 1
            
            # Get the current score entry
            if idx < len(scores):
                current = scores[idx]
                print(f"Current entry: {current}")
            else:
                current = {"initials": "AAA", "score": 0}
                print("Creating new entry")
            
            # Edit the fields
            new_initials = input(f"Initials ({current.get('initials', 'AAA')}): ").strip()
            if new_initials and new_initials != "-":
                current["initials"] = new_initials.upper()[:3]
                
            new_score = input(f"Score ({current.get('score', 0)}): ").strip()
            if new_score and new_score != "-":
                try:
                    current["score"] = int(new_score)
                except ValueError:
                    print("Invalid score. Using previous value.")
            
            # Update or append the entry
            if idx < len(scores):
                scores[idx] = current
            else:
                # Add new entries if needed
                while len(scores) < idx:
                    scores.append({"initials": "AAA", "score": 0})
                scores.append(current)
            
            # Show the updated entry
            print(f"Updated entry: {current}")
            
        except ValueError:
            print("Please enter a valid number")
    
    # Sort scores by score value in descending order
    scores.sort(key=lambda x: x.get("score", 0), reverse=True)
    
    # Trim to 20 entries if needed
    if len(scores) > 20:
        scores = scores[:20]
    
    return scores


def main():
    # Read high scores
    print("READ")
    scores = read_highscores()
    print("SCORES Now:")
    for score in scores:
        print(score)


    #for key, value in scores.items():
    #    print(f"{key}: {value}")

    # Edit 
    new_scores = edit_scores(scores)



    # Write updated configuration back to storage
    write_highscores(new_scores)

    print("\n SCORES Now:")
    for score in new_scores:
        print(score)
    ScoreTrack.place_machine_scores

if __name__ == "__main__":
    main()

