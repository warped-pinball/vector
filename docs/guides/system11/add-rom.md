<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">System 9 & 11 WiFi App Note: New Game ROM Profile</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>



Collect the data needed to add support for new System 9 or 11 titles.

## Overview

Each System 9 or 11 title stores data in different memory locations and formats. The SYS9&11.WiFi board needs a dedicated profile for gathering scores and leader data. Install the board and select **GenericSYS11** (works for System 9 too), then connect over Wi-Fi to use the browser interface.

**Note:** In Generic mode the board cannot show the IP address.

### Finding the IP address

1. Log into your Wi-Fi router and look up the IP address in connected devices.
2. Put the SYS11.WiFi board into Wi-Fi setup mode by holding the black button while powering up. Release after the LED blinks fast, connect with your phone, and read the IP at the bottom of the screen.
3. If another Warped Pinball board is powered on, the boards link within a few minutes. Click the game name in the top-left of the browser to switch between them.

### Capturing memory snapshots

1. Factory reset the game (press advance to AD#70 and select **Yes** on SYS11). Wait for attract mode.
2. Download memory values from the Admin page. Save as `GameName_Baseline.txt`.
3. Start a single-player game and leave Ball 1 in the shooter lane. Save as `GameName_1Player_player1up_Ball1.txt`.
4. Play Ball 1, pause on Ball 2, and include the Player 1 score in the filename (replace `yyyyy`). Save as `GameName_1player_player1up_Ball2_yyyyy.txt`.
5. Start a 3-player game, play up to player 2 at Ball 3, with player 2 active record each score and save a file as: `GameName_3player_player2up_Ball3_score1_score2_score3.txt`.

### System 11 only

6. Record high-score leader initials and values. Save a file with that data in the name:  `GameName_highscores_RED2300000_BLU2000000_GRN1000000_ORG20000.txt`
7. Enter service menu item 49 (Custom Message). Use **Change** and **Advance** to enter the custom message. fill the first line with all 'A' second with 'B' etc. Confirm it appears in attract mode. Save as `GameName_Message.txt`.
8. Turn the custom message **OFF** (AD#49), exit out of the service menu. Then save as `GameName_MessageOFF.txt`.


### Additional snapshots

13. Email all files plus the game software version (shown on power-up or on your rom chip label) to [roms@WarpedPinball.com](mailto:roms@WarpedPinball.com).


**Game Name:** _______________________________

**ROM Version:** _______________________________

#### High scores (attract mode)

1. Initials ________ Score _______________
2. Initials ________ Score _______________
3. Initials ________ Score _______________
4. Initials ________ Score _______________

