<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">System 11 WiFi Module Installation and Use Manual</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>

Indicators, installation steps, WiFi setup, and operational notes for Vector.

## Which board do you have?

This manual covers the **newer Warped Pinball board** for System 11 games.

| Newer board (this manual) | Original board |
| --- | --- |
| ![Newer Warped Pinball Vector board](../../img/sys11/sys9_new_board.png) | ![Original Warped Pinball System 11 / System 9 board](../../img/sys11/board.png) |
| |

**Have the original board?** It is still fully supported and fully software compatible. Use the
[System 11 manual for the original board](manual_OG.md) instead.

## Table of contents

- [Which board do you have?](#which-board-do-you-have)
- [How it works](#how-it-works)
- [Indicators and controls](#indicators-and-controls)
- [LED codes](#led-codes)
- [Disclaimer](#disclaimer)
- [Hardware installation](#hardware-installation)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Web interface](#web-interface)
- [Sound at power-up](#sound-at-power-up)
- [Support](#support)

## How it works

The Vector board installs between the processor chip and the game’s main board, mimicking the RAM chip that stores game settings. Gameplay remains unchanged while the board stores RAM values in permanent memory, eliminating batteries or NVRAM modifications. Installation requires no soldering or permanent changes.

## Indicators and controls

| ![New board with the Status LED and WiFi Configure Button marked](../../img/sys11/sys9_new_board_indicators.png) | <strong>Status LED:</strong><br><span style="white-space:nowrap"><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><g stroke="#f5d90a" stroke-width="1.6" stroke-linecap="round"><line x1="13.5" y1="9.0" x2="17.0" y2="9.0"/><line x1="9.0" y1="13.5" x2="9.0" y2="17.0"/><line x1="4.5" y1="9.0" x2="1.0" y2="9.0"/><line x1="9.0" y1="4.5" x2="9.0" y2="1.0"/></g><circle cx="9" cy="9" r="3.2" fill="#f5d90a"/></svg><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><g stroke="#f5d90a" stroke-width="1.6" stroke-linecap="round"><line x1="13.5" y1="9.0" x2="17.0" y2="9.0"/><line x1="12.2" y1="12.2" x2="14.7" y2="14.7"/><line x1="9.0" y1="13.5" x2="9.0" y2="17.0"/><line x1="5.8" y1="12.2" x2="3.3" y2="14.7"/><line x1="4.5" y1="9.0" x2="1.0" y2="9.0"/><line x1="5.8" y1="5.8" x2="3.3" y2="3.3"/><line x1="9.0" y1="4.5" x2="9.0" y2="1.0"/><line x1="12.2" y1="5.8" x2="14.7" y2="3.3"/></g><circle cx="9" cy="9" r="3.2" fill="#f5d90a"/></svg> &nbsp;Trying to join WiFi</span><br><span style="white-space:nowrap"><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><g stroke="#2fae4a" stroke-width="1.6" stroke-linecap="round"><line x1="13.5" y1="9.0" x2="17.0" y2="9.0"/><line x1="9.0" y1="13.5" x2="9.0" y2="17.0"/><line x1="4.5" y1="9.0" x2="1.0" y2="9.0"/><line x1="9.0" y1="4.5" x2="9.0" y2="1.0"/></g><circle cx="9" cy="9" r="3.2" fill="#2fae4a"/></svg><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><g stroke="#2fae4a" stroke-width="1.6" stroke-linecap="round"><line x1="13.5" y1="9.0" x2="17.0" y2="9.0"/><line x1="12.2" y1="12.2" x2="14.7" y2="14.7"/><line x1="9.0" y1="13.5" x2="9.0" y2="17.0"/><line x1="5.8" y1="12.2" x2="3.3" y2="14.7"/><line x1="4.5" y1="9.0" x2="1.0" y2="9.0"/><line x1="5.8" y1="5.8" x2="3.3" y2="3.3"/><line x1="9.0" y1="4.5" x2="9.0" y2="1.0"/><line x1="12.2" y1="5.8" x2="14.7" y2="3.3"/></g><circle cx="9" cy="9" r="3.2" fill="#2fae4a"/></svg> &nbsp;WiFi joined, all OK</span><br><span style="white-space:nowrap"><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><g stroke="#6a2c91" stroke-width="1.6" stroke-linecap="round"><line x1="13.5" y1="9.0" x2="17.0" y2="9.0"/><line x1="9.0" y1="13.5" x2="9.0" y2="17.0"/><line x1="4.5" y1="9.0" x2="1.0" y2="9.0"/><line x1="9.0" y1="4.5" x2="9.0" y2="1.0"/></g><circle cx="9" cy="9" r="3.2" fill="#6a2c91"/></svg><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><g stroke="#6a2c91" stroke-width="1.6" stroke-linecap="round"><line x1="13.5" y1="9.0" x2="17.0" y2="9.0"/><line x1="12.2" y1="12.2" x2="14.7" y2="14.7"/><line x1="9.0" y1="13.5" x2="9.0" y2="17.0"/><line x1="5.8" y1="12.2" x2="3.3" y2="14.7"/><line x1="4.5" y1="9.0" x2="1.0" y2="9.0"/><line x1="5.8" y1="5.8" x2="3.3" y2="3.3"/><line x1="9.0" y1="4.5" x2="9.0" y2="1.0"/><line x1="12.2" y1="5.8" x2="14.7" y2="3.3"/></g><circle cx="9" cy="9" r="3.2" fill="#6a2c91"/></svg> &nbsp;AP mode: join with your phone</span><br><br><span style="white-space:nowrap"><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><circle cx="9" cy="9" r="6.5" fill="#d7262b" stroke="#00000033" stroke-width="1"/></svg><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><circle cx="9" cy="9" r="6.5" fill="#f5d90a" stroke="#00000033" stroke-width="1"/></svg> &nbsp;Hardware installation issue</span><br><span style="white-space:nowrap"><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><circle cx="9" cy="9" r="6.5" fill="#283a8f" stroke="#00000033" stroke-width="1"/></svg><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><circle cx="9" cy="9" r="6.5" fill="#f5d90a" stroke="#00000033" stroke-width="1"/></svg> &nbsp;WiFi password wrong</span><br><span style="white-space:nowrap"><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><circle cx="9" cy="9" r="6.5" fill="#283a8f" stroke="#00000033" stroke-width="1"/></svg><svg width="18" height="18" viewBox="0 0 18 18" style="vertical-align:middle"><circle cx="9" cy="9" r="6.5" fill="#6a2c91" stroke="#00000033" stroke-width="1"/></svg> &nbsp;WiFi network not found</span><br><br><strong>WiFi Configure Button:</strong> Hold during power up and release when LED flashes for AP mode |
| --- | --- |

## LED codes

The Status LED uses color combinations to indicate system status and faults. Each fault code consists of two color blinks separated by a brief pause.

### Normal Operation
| LED Pattern | Status |
| --- | --- |
| Yellow-Yellow (dim) | Trying to join WiFi at startup |
| Green-Green (dim) | WiFi connected, all systems OK |
| Purple-Purple (dim) | AP mode - join with your phone |

### Hardware Faults (First blink: RED)
| LED Pattern | Code | Description |
| --- | --- | --- |
| Red-Yellow | HDWR01 | Early Bus Activity |
| Red-White | HDWR02 | No Bus Activity |
| Red-Purple | HDWR00 | Unknown Hardware Error |

### WiFi Faults (First blink: BLUE)
| LED Pattern | Code | Description |
| --- | --- | --- |
| Blue-Yellow | WIFI01 | Invalid WiFi Credentials (wrong password) |
| Blue-Purple | WIFI02 | No WiFi Signal (network not found) |
| Blue-Red | WIFI00 | Unknown WiFi Error |

### Configuration Faults (First blink: WHITE)
| LED Pattern | Code | Description |
| --- | --- | --- |
| White-Yellow | CONF01 | Invalid Configuration |
| White-Purple | CONF00 | Unknown Configuration Error |

### Software Faults (First blink: YELLOW)
| LED Pattern | Code | Description |
| --- | --- | --- |
| Yellow-Red | SFTW01 | Drop Through |
| Yellow-White | SFTW02 | Async loop interrupted |
| Yellow-Purple | SFWR00 | Unknown Software Error |

### Other
| LED Pattern | Code | Description |
| --- | --- | --- |
| White | DUNO00 | Unknown Error |

**Note:** Multiple faults will be displayed in sequence with a pause (black) between each fault code.

## Disclaimer

Removing and reseating chips carries risk. Work with the game powered off but grounded, discharge static on the metal backplane, and verify sockets and ICs are fully seated. Ensure correct fuse sizes. Warped Pinball offers email support but cannot be liable for damage.

## Hardware installation

1. Remove the main processor (`MC6802`) from the game board and insert it into the Vector socket, confirming pins are straight and fully seated.

![MC6802 processor location on the System 11 main board](../../img/sys11/chip_location.png)

2. Insert the supplied pin-strip headers into the main-board processor socket, pressing firmly until fully seated.

![Pin strip headers](../../img/sys11/pin_strip.jpg)

3. Attach the adhesive standoff to the Vector board with the provided plastic screw. **Do not remove the backing from the adhesive pad**; rotate the standoff so it sits mostly underneath the board, resting on the resistors. Align the board with the socket and inspect all corners to confirm proper seating.

![Standoff attached to the board](../../img/sys11/standoff.png)

4. <a id="reset-clip"></a>Clip the white wire with the micro clip to the junction of `R55` and `R56` (either component on the correct side). This synchronizes resets on power-up.

Clip location at R55 and R56:

![Reset clip location at R55 and R56](../../img/sys11/clip_to_location.png)

Completed installation:

![New board installed on a System 11 main board](../../img/sys11/sys11_new_board_installed.png)

After installation the game operates normally while Vector provides NVRAM service. Additional features require WiFi configuration.

**First power-up:** The Warped Pinball board works like an NVRAM kit, so your game's settings are restored to factory defaults the first time you power up. You may need to hold the **Advance** button on the coin door during that first power-up to initialize the configuration.

## Connecting to local WiFi

1. Power on the machine. The Status LED shows yellow, then flashes purple (AP mode).
2. Join the **Warped Pinball** network from a phone or computer and ignore “no internet” warnings.

![Join the Warped Pinball network](../../img/sys11/Installation_select_AP.png)

3. If a captive portal does not appear, open a browser to reach the configuration page.

![Sign in to the configuration page](../../img/sys11/Installation_sign_in_button.png)

4. On the configuration page:
   - Select your WiFi SSID and password.
   - Choose your game from the dropdown or select **GenericSystem11** if not listed.
   - Optionally set an admin password to protect actions such as clearing scores.
   - If the board previously joined a network, its last IP address appears on this screen.

![Configuration page](../../img/sys11/Installation_AP_setup_screen.png)

5. Click **Save**, power-cycle the machine, and allow it to reconnect. Yellow means it is joining your WiFi; green means it is connected and all is OK.
6. If joining fails, check the [LED codes](#led-codes) (a blue first blink means a WiFi problem). Power down, hold the WiFi Configure Button while powering up, release when the LED flashes, and repeat setup.

**Pro Tip:** To re-enter configuration mode later, hold the WiFi Configure Button during power-up and release when the LED flashes.

## IP addresses

- The router assigns an IP address to each Vector device (e.g., `192.168.1.239`).
- Access the machine by entering its IP address in a browser on the same network.
- Machines periodically display their IP address on the game display; note changes if the router reassigns addresses.
- For stability, configure a static IP in your router once the device is visible in the connected devices list.

Example: IP address `192.168.1.189` displayed on a Pin•Bot machine.

![IP address shown on a Pin•Bot display](../../img/sys11/ip_on_display.png)

## Web interface

- **Game name** is shown in the upper left. If it is not correct, check your AP mode configuration.
- **Navigation** is in the upper right.
- Note the 20-position leaderboard — it will fill up as you play new games.

![Main web page](../../img/sys11/Installation_vector_screen_main.png)

- A game in play is shown on the same screen (see below).
- Note the ball in play and scores update as you play.
- Something not looking correct? Check your ROM version. On game bootup the ROM version is generally displayed on the screen — make sure you pick that ROM version when configuring your Warped Pinball board in AP mode. If you have a ROM that isn't supported, please contact us; we add ROMs regularly.

![Game in play web page](../../img/sys11/Installation_vector_screen_game_in_play.png)

- Click on **Players** to see and edit the active players list.
- All players get individual best boards.
- Initials are entered on the left and full name on the right.

![Players web page](../../img/sys11/Installation_vector_screen_players.png)

- The top of the admin page shows several setup options.
- **Tournament mode** just saves all scores to the tournament list (and not your normal leaderboard).
- **Score claim: on machine** will cause all players to enter initials to claim their scores after playing (this also records to the individual best boards).
- If you don't want to enter initials every play, you can try **Web interface** — with this feature you claim your score on a web browser after you play.
- Then a section of **adjustment profiles** — use the normal coin door buttons to set up a profile, then enter a name and click capture here to save those settings. You can save and restore up to four.
- Normally the display will show the IP address in attract mode; you can turn this off here.
- Prevent automatic credit awards during initials entry by setting adjustments 18, 19, 20, and 21 to `0` using the coin-door controls.

![Admin page, top](../../img/sys11/Installation_vector_screen_admin_top.png)

**Example of score claim on front page (note the section at the bottom of the screen)**

![Example of score claim on front page](../../img/sys11/Installation_vector_screen_score_claim.png)

- **Software update process:** just check the Yellow button — it will let you know when there is a software update available.
- The button will also show if the update server was unreachable — if so, just look again later.
- **Upload Developer Build** is used for test versions when directed by Warped Pinball staff.
- The remaining button controls are self-explanatory.

![Admin page, bottom](../../img/sys11/Installation_vector_screen_admin_bottom.png)

- Use the WiFi status to determine if you have a strong connection.
- Switch diagnostics are shown in the grid of colors at the end of the admin page.

![Admin page, switch diagnostics](../../img/sys11/Installation_vector_screen_admin_end.png)

**A note about the software update process:** The Yellow button is the preferred method and takes about 2 minutes to complete. The game will automatically reboot at the end of the process. Check the bottom of any page for the currently installed software version (note that each type of game — WPC, System 11, Data East, EM, etc. — has its own version numbers). In case of trouble (unusual), there is an available program to reload the software via USB cable from a computer. See the [instructions here](https://github.com/warped-pinball/trench-coat/blob/main/Trench-Coat-Install-Guide.md).

Watch the [features video](https://youtu.be/eGVe5E9X-2I) and send ideas via [WarpedPinball.com](https://WarpedPinball.com).

## Sound at power-up

Some System 11B and 11C games make a sound at power-up. There is a jumper included in your kit to prevent this sound.

You can add a capacitor to the sound board right on top of (in parallel with) the existing capacitor `C15`; a 4.7 µF capacitor rated 10 V or more works well. Or use the included jumper as shown in the pictures below: jumper the test point loop on Vector to the left side of capacitor `C15`.

Sound board, with the connection area circled:

![Sound board with the connection area circled](../../img/sys11/sound_board.png)

Jumper location on your Vector board:

![Jumper location on the Vector board](../../img/sys11/sound_clip_location1.png)

Jumper location on the sound board:

![Jumper location on the sound board](../../img/sys11/sound_clip_location2.png)

## Support

Need help or have feature ideas? Visit [WarpedPinball.com](https://WarpedPinball.com).

This Warped Pinball product is patent pending.
