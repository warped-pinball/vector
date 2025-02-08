# live game status updates
import SharedState as S
from Shadow_Ram_Definitions import shadowRam, SRAM_DATA_LENGTH, SRAM_DATA_BASE, SRAM_COUNT_BASE
import json
import time

class GameStatus:
    def __init__(self):
        self.game_active = False
        self.number_of_players = 0
        self.time_game_start = None
        self.time_game_end = None
        self.poll_state = 0


    def BCD_to_Int(self, number_BCD):
        """ convert BDC number from machine to regular int"""
        number_int = 0
        for byte in number_BCD:
            high_digit = byte >> 4
            low_digit = byte & 0x0F
            if low_digit > 9:
                low_digit = 0
            if high_digit > 9:
                high_digit = 0
            number_int = number_int * 100 + high_digit * 10 + low_digit
        return number_int


    def get_machine_score(self, index):
        """ read live score from machine memory (0=player1, 3=player4) """
        try:
            score = 0
            if S.gdata.get("InPlayScores", {}).get("Type", 0) != 0:
                score_start = S.gdata["InPlayScores"]["ScoreAdr"] + index * S.gdata["InPlayScores"]["BytesInScore"]
                score_bytes = shadowRam[score_start:score_start + S.gdata["InPlayScores"]["BytesInScore"]]
                score = self.BCD_to_Int(score_bytes)
            else:
                print("GSTAT: InPlayScores not defined")
            return score
        except Exception as e:
            print(f"GSTAT: error in get_machine_score: {e}")
        return 0



    def get_ball_in_play(self):
        """ get Ball in play number, 0=game over """
        try:
            ball_in_play = S.gdata["BallInPlay"]
            if ball_in_play["Type"] == 1:
                ball_token = shadowRam[ball_in_play["Address"]]
                ball_values = {
                    ball_in_play["Ball1"]: 1,
                    ball_in_play["Ball2"]: 2,
                    ball_in_play["Ball3"]: 3,
                    ball_in_play["Ball4"]: 4,
                    ball_in_play["Ball5"]: 5
                }
                # return 0 if no match (game over can be 0x3F or 0xFF on some games)
                return ball_values.get(ball_token, 0)
        except Exception as e:
            print(f"GSTAT: error in get_ball_in_play: {e}")
        return 0


    def report(self, request):
        """ generate a report of the current game status, return in Json format """
        report_data = {}

        try:
            report_data["BallInPlay"] = self.get_ball_in_play()
            report_data["Player1Score"] = self.get_machine_score(0)
            report_data["Player2Score"] = self.get_machine_score(1)
            report_data["Player3Score"] = self.get_machine_score(2)
            report_data["Player4Score"] = self.get_machine_score(3)

            # game time
            if self.time_game_start is not None:
                if self.game_active:
                    report_data["GameTime"] = (time.ticks_ms() - self.time_game_start) / 1000
                elif self.time_game_end > self.time_game_start:
                    report_data["GameTime"] = (self.time_game_end - self.time_game_start) / 1000
                else:
                    report_data["GameTime"] = 0
            else:
                report_data["GameTime"] = 0

            report_data["GameActive"] = self.game_active

        except Exception as e:
            print(f"GSTAT: Error in report generation: {e}")

        # Return the collected report data as JSON
        print("GSTAT: Report Data:", json.dumps(report_data))
        return json.dumps(report_data)

  

    def poll_fast(self):
        """ not too sure we need this? - poll for game start and end time """
        if self.poll_state == 0:
            # watch for ball in play for game start
            self.game_active = False
            if self.get_ball_in_play() != 0:
                self.time_game_start = time.ticks_ms()
                self.game_active = True
                print("GSTAT: start game @ time=", self.time_game_start)
                self.poll_state = 1
        elif self.poll_state == 1:
            if self.get_ball_in_play() == 0:
                self.time_game_end = time.ticks_ms()
                print("GSTAT: end game @ time=", self.time_game_end)
                self.game_active = False
                self.poll_state = 2
        else:
            self.poll_state = 0


if __name__ == "__main__":
    import GameDefsLoad
    GameDefsLoad.go()
    game_status = GameStatus()
    print(game_status.report("ok"))
    game_status.poll_fast()