<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">System EM Vector Installation and Use Manual</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>



How the Vector board installs on an Electro-Mechanical pinball machine, what the buttons and indicators mean, and how to bring your EM online.

## Table of contents

- [How it works](#how-it-works)
- [Indicators and controls](#indicators-and-controls)
- [Disclaimer](#disclaimer)
- [Hardware installation - main board mounting](#hardware-installation-main-board-mounting)
- [Hardware installation - power and Game Over](#hardware-installation-power-and-game-over)
- [Hardware installation - score reel sensors](#hardware-installation-score-reel-sensors)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Configure your game](#configure-your-game)
- [Sensor adjustment](#sensor-adjustment)
- [Training games and learn mode](#training-games-and-learn-mode)
- [Problems? Updates?](#problems-updates)

## How it works

The circuit board is installed in the back box of your Electro-Mechanical pinball machine. You will make alligator clip connections to general illumination power and also to the "Game Over" bulb. A special sensor assembly is attached to each score reel solenoid with a wire tie. There is no soldering required and no permanent modification of the machine.

## Indicators and controls

| ![EM board layout](../../img/em/board_layout.jpg) | **WiFi Configure Button**<br>Hold during power up, release when LED flashes, for setup mode<br><br>**WiFi Status LED**<br>Fast blink = AP mode<br><br>**Sensor sensitivity adjustment buttons** (+ / -)<br><br>**Number display**<br>WiFi IP address shown here<br><br>**Score reel sensor indicators**<br>(under each connector) |
| --- | --- |

## Disclaimer

While we make every effort to make this an easy and safe process, damage to your game is possible and we cannot be responsible if something goes wrong. If you have never worked on EM games we encourage you to find someone who has and offer them some pizza to come help.

Some things to watch for: static electricity can damage circuits. When working with the circuit board it is not a bad idea to touch the metal backplane before you touch electronics - just to make sure that charge you got walking across the carpet is gone.

We offer email support and will do anything we can to help you enjoy Warped Pinball accessories. We cannot however be liable for any damage to yourself or machine.

## Hardware installation - main board mounting

SYS EM.Wifi main board will be installed on the inside of your back box. It is best to place the board on the inside of the vertical side wall. Every game is a little different, you want to find a spot where game wires will not touch the board and there is not a metal back plate to interfere with WiFi. Before committing to a location check score reel sensor cable lengths. There is a pack of short sensor leads and one with long sensor leads - make sure you mount the main board in a location where the required sensor leads can reach the score reel coils.

The included mounting screws fit into and through the board plastic standoff spacers as shown. (Two are shown here - you can use all four if you want.)

![EM board mounted in backbox](../../img/em/board_mounted.jpg)

## Hardware installation - power and Game Over

The board is powered by the general illumination AC voltage in the back box. Find an easy place to measure any bulb that stays on all the time with an AC voltmeter.

Confirm your voltage is between 5.5 and 10 Volts AC as shown:

![Checking GI voltage with a multimeter](../../img/em/voltmeter_check.jpg)

With the game turned off, make the power connections with the included alligator clips as shown. An extender cable (included) can then be used to connect power to the main board in the upper left corner. (Red and black are interchangeable.)

![Power connection with alligator clips](../../img/em/power_alligator_clips.jpg)

![Power connected to the main board](../../img/em/power_connected.jpg)

Use the second set of alligator clips and extension wire to connect the Game Over lamp in the back box to the main board, right next to the number display. There is no need to measure voltage here. The black and red clips are interchangeable (don't worry about a ground or negative connection) - just get the clips on each side of the Game Over lamp.

![Game Over lamp connection](../../img/em/game_over_connection.jpg)

## Hardware installation - score reel sensors

Plan a location for the sensor on the coils of each score reel. All sensors must be placed at the same rotation position on all coils. In many older machines the top of the coil is possible and is the ideal spot. Newer games have a metal bracket in the way - in this case mount all the sensors at about the 11:00 position looking at the back of the coils.

Reels are always numbered 1, 10, 100, 1000, etc. from left to right as you look into the back box. Always use the "1" position on the circuit board - even in the case where you have dummy reels in the game.

![Score reel numbering including a dummy reel](../../img/em/reel_numbering.jpg)

Attach each sensor to a wire assembly before installing on the coil. If your coil paper is damaged you can use the included high-temperature tape dots to repair it before placing sensors. Use the longer wire ties - feeding around the coil and through the loop on the sensor circuit board. Note the "upside down" orientation of the sensor on the coil.

![Sensor assembly with connector](../../img/em/sensor_assembly.jpg)

| ![Sensor mounted at top of coil](../../img/em/sensor_mount_top.jpg) | ![Sensor mounted with bracket clip](../../img/em/sensor_mount_bracket.jpg) |
| --- | --- |

Connect each sensor wire to the main board connectors. The picture below shows the "1" digit for player number one connected. In game setup later you will set how many dummy reels are installed so that your scores scale up correctly.

![Sensors wired to the main board](../../img/em/sensors_connected_board.jpg)

Once all the sensors are connected double check all wiring and wire routing. Keep those wires out of moving parts! There are extra wire ties included to help with this step. Make sure your alligator clips will not short out - tape them up if necessary. Now you are ready to power up the game and get connected to WiFi!

## Connecting to local WiFi

Power up your pinball machine and you will notice the WiFi status LED blinking fast. With a phone or computer open the WiFi configuration and look for a new WiFi network called **Warped Pinball**.

![Selecting the WarpedPinball network](../../img/em/wifi_select_network.png)

**Pro Tip:** To enter configuration mode in the future, press and hold the WiFi config button and power up the machine. Hold the button until you see the LED blink rapidly. This will put you back in setup mode (WiFi AP mode).

Tap **WarpedPinball** and wait a moment. You may see a warning about no internet service, that is ok. You should get a screen similar to this next example with a **Sign In** button. If your phone or computer does not have this, but has joined the WiFi, try opening a browser for the next step.

![Sign in to the WarpedPinball network](../../img/em/wifi_sign_in.png)

In your browser or phone you should see a configure screen. Pick the SSID (the name of your local WiFi network) and enter your WiFi password for that network - please carefully double check for capitalization. You can also pick an Admin Password if you like; this password protects functions in the machine like erasing scores and leaderboards.

If the board has previously joined a WiFi network successfully you will see the IP address it was given at the bottom of this screen.

![Configure Your Vector screen](../../img/em/wifi_configure_screen.png)

When ready just click the Save button. SYS EM.Wifi will remember those WiFi settings and automatically connect to your local WiFi at every power cycle. After pressing Save you can power the game off and on again for the new setting to take effect.

When the board powers up this time you will see the WiFi status LED blink slowly. Then the number display will begin showing the IP address - this is your indication that the SSID and password are correct.

You can reset settings by powering down, then holding down the WiFi setup button while powering up. When you see the LED blink fast, release the button. You can restart the pairing process.

## IP addresses

Each machine connected to your WiFi will be issued an IP address by your local router. The SYS EM.Wifi device does not have control of the IP address as it is assigned by your local WiFi system. IP addresses are four numbers separated by periods, such as `192.168.1.79`. To access one of your machines you will need to type the IP address into the address bar on a browser (Chrome, Microsoft Edge, Safari, etc). Once you connect to a machine, setting a bookmark is a good way to make access simple. After days or weeks of use your WiFi router may pick a new IP address, requiring you to re-enter it on your computer.

SYS EM.Wifi uses the number display on the main board to show you the IP address. Watch the display as the four numbers are blinked slowly by, with periods between each number.

![Number display and status LEDs on the main board](../../img/em/board_display_status.jpg)

All routers have a mechanism to set IP addresses as "static" so it is not changed in the future. Once you have connected to your SYS EM.Wifi board we recommend that you log into your local router, find the IP address in the list of connected devices, and check the box making that address static.

## Configure your game

Open a web browser on any computer on your local WiFi. Type the IP address in the URL bar and you should get the Warped Pinball game screen. Select **Admin** in the upper right corner to get to the page where you configure the game. Input the name, players, reels, and number of dummy (0) reels. Be sure to click **Save Game Config**.

![Admin setup page with game configuration and calibration](../../img/em/admin_setup.png)

## Sensor adjustment

Now set the sensitivity of the coil sensors for your specific game. Take the glass out so you can hit single targets on the playfield one at a time. Watch the green sensor LEDs on the main board while testing targets (good time to have a helper). The green LED under the correct connector should turn on briefly after the score reel increments. When a carry over occurs you will see two LEDs blink, one for each reel that is incremented.

Watch carefully and note if the LED does not blink sometimes when the reel increments. If this is the case just press the "+" button on the main board once and retest. On the other hand if you see too many LEDs come on when reels are not incrementing, press the "-" button on the main board once and retest. Keep adjusting + or - as required until all score reels register correctly on the green LEDs.

## Training games and learn mode

Click **Record Calibration Game** in the Admin panel.

![Record Calibration Game button](../../img/em/admin_record_calibration.png)

Play a normal game with all players. After hitting the start button wait 8 seconds or more to plunge - give the computer time to keep up. During the game the number display on the main board will count up from 0 to 9 as you play. Your game must end at or before 9 is reached. Once the display is at 7 just let balls drain. Let the game end, wait a few seconds, and then continue on the computer. At the end of the game enter the actual scores into the web interface.

When you have at least two games recorded, the **Start Learning Process** button will enable.

![Two calibration games recorded](../../img/em/admin_calibration_recorded.png)

Click the button to start the process. Learning can take up to 15 minutes to complete. The number display on the main board will count down from 9 to 0 during the process. Once complete, your game is ready to play and enjoy online scoring!

## Problems? Updates?

This is a brand new system and board for us - we want to hear your feedback to make it better! When there are software updates the **Update** button on the Admin page will turn yellow. All you need to do is click Update - please do not play the machine during the update process. It only takes a few minutes, you can wait.

![Update button on the Admin page](../../img/em/admin_update_button.png)

The **Clear Browser Storage** button can be useful if the web pages are acting funny or locked up. Two file downloads are available - **Download Logs** and **Download Diagnostic Data**. If Warped is helping you diagnose an issue we will likely ask you to download both of these files and send them to us.

![Reset Tournament Board, Clear Browser Storage, Factory Reset Vector, and Debug buttons](../../img/em/admin_factory_reset.png)

Thanks for your support!
