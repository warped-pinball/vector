<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">WPC WiFi App Note: New Game ROM Profile</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>



Collect memory images so a new WPC title can be profiled for scoring and leaderboard support.

## Process

Install the WPC WiFi board and select **Generic WPC** for the game name. Connect via Wi-Fi so you can use the browser interface. The board cannot show the IP address in this mode, so locate it by:

- Looking up the IP address in your router’s connected devices list.
- Putting the board back into Wi-Fi setup mode (hold the black button while powering up until it blinks fast) and reading the IP at the bottom of the screen.
- Linking from another Warped Pinball game already on the network and switching machines via the game name in the top-left of the browser UI.

Once connected, follow these steps to capture the memory images needed to build a new profile.

1. Factory reset the game if needed.
2. Download a baseline memory file from the Admin page and name it `GameName_Baseline.txt`.
3. Start a single-player game; leave ball #1 in the shooter lane. Download `GameName_1player_ball1.txt`.
4. Play ball #1, pause on ball #2, and include the player 1 score in the filename. Download `GameName_1player_ball2_yyyyy.txt`.
5. Start a three-player game and capture two files with different balls and scores. Include `playerXup` plus scores, e.g. `GameName_3player_ball1_player2up_128756_35463_23765.txt`.
6. Note the Grand Champion initials and score, then download `GameName_GrandChamp_ABC150000.txt` (replace initials/score).
7. Save leader scores in order 1–4 using `GameName_highscores_RED2300000_BLU2000000_GRN1000000_ORG20000.txt`.
8. Enter service menus > utilities > custom message. Fill screens with `A`, `B`, and `C`, exit, and download `GameName_Message.txt`.
9. Turn custom message **off** in adjustments and download `GameName_MessageOFF.txt`.
10. Change two adjustment items near the end of the menu, exit, and download `Adjustments.txt`.
11. Email all files plus the game software version (shown on power-up) to [Inventingfun@gmail.com](mailto:Inventingfun@gmail.com).
12. When an update is ready, click **Update** on the Admin page.
13. Test the update for high score recording, IP display in attract mode, and four high scores on the game display.

This Warped Pinball product is patent pending.
