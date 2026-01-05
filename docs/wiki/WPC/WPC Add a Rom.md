<!-- pdf-download-button:start -->
<a class="pdf-download-button" href="https://raw.githubusercontent.com/wiki/warped-pinball/vector/wiki-pdf/WPC/WPC%20Add%20a%20Rom.pdf" style="display:inline-block;padding:0.45rem 1.1rem;background:#1f4ed8;color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">Download this page as a PDF</a>
<!-- pdf-download-button:end -->

# WPC Wifi App Note: New Game ROM Profile

## What Is This For?

Each System WPC pinball title stores data in slightly different locations with sometimes slightly different formats. So each title requires a “profile” to allow the board to gather scores, set leaders, etc. This application note is intended for someone who has generously offered to help discover the profile and get a new title on the list of supported games. Thank you for your efforts and support!

## Process

1. Install the WPC Wifi board in your game as usual and select **Generic WPC** for the game name.
    Connect via Wi-Fi so you can use the browser-based interface.
    *Note: In this mode the WPC Wifi board cannot show you the IP address.*

    There are three ways to find the IP address:
    1. Log into your local Wi-Fi router and look up the IP address in the list of connected devices.
    2. Put the WPC Wifi board into Wi-Fi setup mode again by holding the black button down while powering up (wait for fast blink before letting go of the button). Connect your phone as before and read the IP address from the bottom of the screen.
    3. If you have another game already fitted with a Warped Pinball board, turn it on as well. In a couple minutes the games will find each other and link. You can transfer between the games by clicking the game name in the top left of the browser screen.

2. Once you are connected to the board with a browser and the game is running, the process is simple: set up certain situations in the game and save memory images on the Admin screen. Just follow the steps in the next section.

> **Option #2 to find IP address**
> Once connected, each test will be saved with the **Download Memory Snapshot** (which can take 25 seconds to complete). Please make sure the web page lists “Generic”. If your game name is listed you can reconfigure for “Generic” in AP mode (hold down the black button while powering up, hold until an LED blinks fast, use a phone to configure from there).

## Step-by-Step Guide

1. Factory reset the game (maybe already done after installing the Warped Pinball Board).
2. Download a file of memory values using the Admin page button.
    Name the file `GameName_Baseline.txt`.
3. Start a single-player game, leave ball #1 in the shooter lane.
    Download another memory values file called `GameName_1player_ball1.txt`.
4. Play ball #1, pause play on ball #2. For “yyyy” place the player 1 score in the file name.
    Download another memory values file called `GameName_1player_ball2_yyyyy.txt`.
5. Repeat with a three-player game—download and rename two files with different ball in play and scores. Add `playerXup`; store a file for player 2 up and another for player 3 up. File names should look like `GameName_3player_ball1_player2up_128756_35463_23765.txt`.
6. Note the Grand Champion initials and score. Download another memory file and rename `GameName_GrandChamp_ABC150000.txt` (fill in the initials and score instead of `ABC150000`).
7. Note the four leader scores and save a file with those initials and scores in order from 1 to 4:
    `GameName_highscores_RED2300000_BLU2000000_GRN1000000_ORG20000.txt`.
8. Enter the service menus, go to utilities and custom message. There are three screens of custom message—enter all `A`s on the first screen, all `B`s on the second, and all `C`s on the third. Exit the service menu system.
    Download another memory values file called `GameName_Message.txt`.
9. Enter service menus, adjustments, and turn the custom message to **OFF**. Exit the service menu system.
    Download another memory values file called `GameName_MessageOFF.txt`.
10. Enter service menus, adjustments, and make changes to two items near the end of the menu (exact items do not matter). Exit the service menu system. Download a file and rename it `Adjustments.txt`.
11. Grab all the files from your downloads folder and email them to `Inventingfun@gmail.com` with the software version of your game (displayed on power-up).
12. You will be notified when an update is ready. Click the **Update** button on the Admin page.
13. Test it out and make sure everything works (high score recording, IP display in attract mode, four high scores on the game display).

_This Warped Pinball product is patent pending status._
