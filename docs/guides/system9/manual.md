<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
   <h1 style="margin: 0;">System 9 WiFi Module Installation and Use Manual</h1>
   <button onclick="window.print()" style="white-space: nowrap;">
      <span aria-hidden="true">🖨️</span> Print This Guide
   </button>
</div>

Setup and operation details for Vector.

## Which board do you have?

This manual covers the **newer Warped Pinball board** for System 9 games.

| Newer board (this manual) | Original board |
| --- | --- |
| ![Newer Warped Pinball Vector board](../../img/sys11/sys9_new_board.png) | ![Original Warped Pinball System 11 / System 9 board](../../img/sys11/board.png) |

**Have the original board?** It is still fully supported and fully software compatible. Use the
[System 9 manual for the original board](manual_OG.md) instead.

## Table of contents

- [Which board do you have?](#which-board-do-you-have)
- [Supported games](#supported-games)
- [How it works](#how-it-works)
- [Indicators and controls](#indicators-and-controls)
- [LED codes](#led-codes)
- [Disclaimer](#disclaimer)
- [Hardware installation](#hardware-installation)
- [Victor's System 9 board](#victors-system-9-board)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Web interface](#web-interface)
- [Support](#support)

## Supported games

- Comet
- Space Shuttle
- Sorcerer

## How it works

The Vector board installs between the processor chip and the game’s main board to emulate the RAM that stores settings. Gameplay runs on the original software, while the board stores RAM values in permanent memory, eliminating batteries or NVRAM mods. It uses the same hardware and firmware as the System 11 board, with game profiles for the System 9 titles.

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

Pulling chips out of classic games carries inherent risk. If you have never re-seated chips, seek help from someone experienced. Work with the game powered off but plugged in for grounding, discharge static on the metal backplane, double-check every pin for full seating, and confirm fuse ratings.

Warped Pinball offers email support and will assist when possible, but cannot be liable for damage to persons or machines.

## Hardware installation

1. **Remove the main processor**
   - Locate the MC6802 processor on the main board.
   - Carefully remove the chip and inspect pins for alignment.

![MC6802 processor location on the System 9 main board](../../img/sys11/sys9_cpu_location.png)

2. **Insert the processor into Vector**
   - Place the MC6802 into the Vector socket.
   - Ensure pins are straight and press evenly until fully seated.
3. **Install pin strip headers**
   - Insert the provided pin strip headers into the main-board processor socket.
   - Press firmly on sections of 3–4 pins until fully seated.

![Pin strip headers](../../img/sys11/pin_strip.jpg)

4. **Mount the Vector board**
   - Attach the standoff using the plastic screw and peel the backing from the adhesive pad (optional, but recommended).
   - Align the board with the socket, verify pin alignment, and press firmly until seated.

![New board installed on a System 9 main board](../../img/sys11/sys9_new_board_installed.png)

5. <a id="reset-clip"></a>**Connect the reset wire**
   - Attach the white micro clip to the junction of `R5` and `R4` (location varies by board orientation).
   - This synchronizes resets during power-up; expect a few extra seconds at startup.
   - This connection is mandatory for proper operation.

![Reset clip at the junction of R5 and R4](../../img/sys11/sys9_clip.png)

After installation the game operates normally and the board provides NVRAM service. Configure WiFi to enable advanced features.

**First power-up:** The Warped Pinball board works like an NVRAM kit, so your game's settings are restored to factory defaults the first time you power up. You may need to hold the **Advance** button on the coin door during that first power-up to initialize the configuration.

## Victor's System 9 board

Vector also works on Victor's red replacement System 9 CPU board. Install it the same way, in the MC6802 processor socket (`U17`), which is just to the right of the **/RESET** test point (`TP6`).

**Pay attention to pin #1 alignment.** Double-check that pin #1 of the processor and pin #1 marked on the Vector board both line up with pin #1 of the `U17` socket before you press anything into place.

On this board, attach the white reset clip to either of these points (both are marked in the photo):

- **Option 1 (preferred):** the bottom lead of resistor `R170`, near the upper left of the board.
- **Option 2:** the **/RESET** test point hole (`TP6`), just to the left of the processor socket.

![Victor's System 9 board, with both reset clip points marked](../../img/sys11/sys9_victor_board_reset_new.png)

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

- Your router assigns an IP address to each machine (e.g., `192.168.1.239`).
- Access the machine by entering its IP in a browser on the same network and bookmark it.
- Routers may change assignments; Vector periodically displays the current IP on the game display.
- Set a static IP in your router once the device is connected for stability.

Example display: IP address `188.168.1.115` shown on a Comet machine.

![IP address shown on a Comet display](../../img/sys11/comet_ip.png)

- All data stays local on the board; nothing is pushed to the internet.
- Access the interface only from devices on the same network via the assigned IP.
- System 9 games display the IP address in place of high scores during attract mode.

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
- **Score claim: on machine** is not available on System 9 games.
- **Score claim: web interface** is the preferred way to claim scores — after playing, claim your score on a web browser.
- Then a section of **adjustment profiles** — use the normal coin door buttons to set up a profile, then enter a name and click capture here to save those settings. You can save and restore up to four.
- Normally the display will show the IP address in attract mode; you can turn this off here.

![Admin page, top](../../img/sys11/Installation_vector_screen_admin_top.png)

**Example of score claim on front page (note the section at the bottom of the screen)**

![Example of score claim on front page](../../img/sys11/Installation_vector_screen_score_claim.png)

- **Software update process:** just check the Yellow button — it will let you know when there is a software update available.
- The button will also show if the update server was unreachable — if so, just look again later.
- **Upload Developer Build** is used for test versions when directed by Warped Pinball staff.
- The remaining button controls are self-explanatory.

![Admin page, bottom](../../img/sys11/Installation_vector_screen_admin_bottom.png)

- Use the WiFi status to determine if you have a strong connection.

![WiFi status](../../img/sys11/sys11_wifi.png)

**A note about the software update process:** The Yellow button is the preferred method and takes about 2 minutes to complete. The game will automatically reboot at the end of the process. Check the bottom of any page for the currently installed software version (note that each type of game — WPC, System 11, Data East, EM, etc. — has its own version numbers). In case of trouble (unusual), there is an available program to reload the software via USB cable from a computer. See the [instructions here](https://github.com/warped-pinball/trench-coat/blob/main/Trench-Coat-Install-Guide.md).

Watch the [features video](https://youtu.be/eGVe5E9X-2I) and send ideas via [WarpedPinball.com](https://WarpedPinball.com).

## Support

Need help or have feature ideas? Visit [WarpedPinball.com](https://WarpedPinball.com).
