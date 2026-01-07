# System 9 & 11 WiFi App Note: New Game ROM Profile

Back to [all guides](../index.md).

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
3. Start a single-player game and leave Ball 1 in the shooter lane. Save as `GameName_PL1_Ball1.txt`.
4. Play Ball 1, pause on Ball 2, and include the Player 1 score in the filename (replace `yyyyy`). Save as `GameName_PL1_Ball2_yyyyy.txt`.
5. Start a 3-player game, play through Ball 3, and record each score. Save as `GameName_PL3_Ball3_score1_score2_score3.txt`.

### System 11 only

6. Record high-score leader initials and values. Save as `GameName_leaderboard/txt`.
7. Enter service menu item 49 (Custom Message). Use **Change** and **Advance** to enter the message from the data sheet. Confirm it appears in attract mode. Save as `GameName_Message.txt`.
8. Turn the custom message **OFF** (AD#49). Save as `GameName_MessageOFF.txt`.
9. Record high-score initials and scores on the data sheet.

### Additional snapshots

10. Drop a coin and save as `GameName_Coin1.txt`.
11. Drop another coin and save as `GameName_Coin2.txt`.
12. Drop a third coin and save as `GameName_Coin3.txt`.
13. Send all files plus the completed data sheet (scan or photo) to [Inventingfun@gmail.com](mailto:Inventingfun@gmail.com).
14. When you receive `GameName.JSON`, download it via the Admin page. Enter Wi-Fi setup (hold button during power-up until fast blink) and select the new file.
15. Test the game: verify high-score recording, IP display in attract mode, and four high scores on the display.

## File checklist

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

This Warped Pinball product is patent pending.

### Data sheet

**Game Name:** _______________________________

**ROM Version:** _______________________________

#### High scores (attract mode)

1. Initials ________ Score _______________
2. Initials ________ Score _______________
3. Initials ________ Score _______________
4. Initials ________ Score _______________

#### Custom message

Provide the exact message entered.

##### For 16-character × 3-line games

```
A A A
(space × 10) A A A
Fill between the B’s with punctuation (‘ / ” . @ *)
B B B B B B
Center line with periods:
C C C C. C. Z. Z. 0 1 2 3 4 C C C
```

##### For 7-character × 6-line games

```
A A
(space × 3) A A B B
(space × 3) B B
Fill between the C/Ds with punctuation (‘ / ” . @ *)
C C C C D D D D
Center line with periods:
E E A. B. C. E E F F 0 1 2 F F
```
