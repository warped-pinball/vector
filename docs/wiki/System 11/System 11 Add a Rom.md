<!-- pdf-download-button:start -->
<a class="pdf-download-button" href="https://raw.githubusercontent.com/wiki/warped-pinball/vector/wiki-pdf/System%2011/System%2011%20Add%20a%20Rom.pdf" style="display:inline-block;padding:0.45rem 1.1rem;background:#1f4ed8;color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">Download this page as a PDF</a>
<!-- pdf-download-button:end -->

# System 9 and 11 WiFi App Note: New Game ROM Profile

## Overview
Each System 9 or 11 pinball title stores game data in different memory locations and formats. To gather scores, set leaders, and support new titles, the SYS9&11.WiFi board needs a dedicated profile. This application note guides you through collecting the data required to build that profile. Thank you for helping expand the list of supported games.

## Process
Install the SYS9&11.WiFi board in your game as usual and select **GenericSYS11** for the game name. Note that **Generic SYS11** also works for System 9. Connect over Wi-Fi so you can use the browser interface.

> **Note:** In Generic mode the SYS11.WiFi board cannot show the IP address.

### Finding the IP Address
1. Log into your Wi-Fi router and look up the IP address in the list of connected devices.
2. Put the SYS11.WiFi board into Wi-Fi setup mode by holding the black button while powering up. Release after the LED blinks fast, connect with your phone, and read the IP address at the bottom of the screen.
3. If another game with a Warped Pinball board is powered on, the boards will link within a few minutes. Click the game name in the top-left of the browser to switch between them.

### Capturing Memory Snapshots
Once connected through a browser and the game is running, follow these steps:

1. Factory reset the game (press advance to AD#70 and select **Yes** on SYS11). Wait for attract mode.
2. Download memory values from the Admin page. Save as `GameName_Baseline.txt`.
3. Start a single-player game and leave Ball 1 in the shooter lane. Save as `GameName_PL1_Ball1.txt`.
4. Play Ball 1 and pause on Ball 2. Include the Player 1 score in the filename (replace `yyyyy`). Save as `GameName_PL1_Ball2_yyyyy.txt`.
5. Start a 3-player game, play through Ball 3, and record each score. Save as `GameName_PL3_Ball3_score1_score2_score3.txt`.

### System 11 Only
6. Record high-score leader initials and values. Save as `GameName_leaderboard/txt`.
7. Enter service menu item 49 (Custom Message). Use **Change** and **Advance** to enter the message from the data sheet. Confirm it appears in attract mode. Save as `GameName_Message.txt`.
8. Turn the custom message **OFF** (AD#49). Save as `GameName_MessageOFF.txt`.
9. Record high-score initials and scores on the data sheet.

### Additional Snapshots
10. Drop a coin and save as `GameName_Coin1.txt`.
11. Drop another coin and save as `GameName_Coin2.txt`.
12. Drop a third coin and save as `GameName_Coin3.txt`.
13. Send all files plus the completed data sheet (scan or photo) to `Inventingfun@gmail.com`.
14. When you receive `GameName.JSON`, download it via the Admin page. Enter Wi-Fi setup (hold button during power-up until fast blink) and select the new file.
15. Test the game: verify high-score recording, IP display in attract mode, and four high scores on the display.

## File Checklist
- `GameName_Baseline.txt`
- `GameName_Ball1_xxx.txt`
- `GameName_Ball2_xxx.txt`
- `GameName_Ball3_xxxx.txt`
- `GameName_GameOver.txt`
- `GameName_Message.txt`
- `GameName_MessageOFF.txt`
- `GameName_Coin1.txt`
- `GameName_Coin2.txt`
- `GameName_Coin3.txt`

> This Warped Pinball product is patent pending.

## Data Sheet
- **Game Name:** _______________________________
- **ROM Version:** _______________________________

### High Scores (attract mode)
1. Initials ________ Score _______________
2. Initials ________ Score _______________
3. Initials ________ Score _______________
4. Initials ________ Score _______________

### Custom Message
Provide the exact message entered.

#### For 16-character × 3-line games
```
A A A
(space × 10) A A A
Fill between the B’s with punctuation (‘ / ” . @ *)
B B B B B B
Center line with periods:
C C C C. C. Z. Z. 0 1 2 3 4 C C C
```

#### For 7-character × 6-line games
```
A A
(space × 3) A A B B
(space × 3) B B
Fill between the C/Ds with punctuation (‘ / ” . @ *)
C C C C D D D D
Center line with periods:
E E A. B. C. E E F F 0 1 2 F F
```
