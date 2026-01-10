<div style="position: fixed; top: 1rem; right: 1rem; z-index: 1000;">
  <button onclick="window.print()">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>

# System 11 WiFi Quick Start (v1.1)

[Back to All Guides](../index.md)

Fast-path instructions for installing the Warped Pinball System 11 WiFi board.

## Steps

Check out installation videos at [WarpedPinball.com](https://WarpedPinball.com). For System 9 installs, use the dedicated guide on the site.

1. Power off the pinball machine.
2. Remove the main processor chip from the System 11 board. Place it into the Warped Pinball System 11 WiFi board’s 40-pin socket, matching pin #1 and checking for bent pins.
3. Insert the pin strips into the main board socket. Press firmly on each pin so it seats fully.
4. Insert the round-pin chip carrier into the socket strips.
5. Attach the sticky standoff and screw to the System 11 PCB and peel the backing.
6. Place the board into the main-board socket, confirm all pins are seated, and make sure the processor orientation matches the original.
7. Inspect the reset circuit for modifications. Clip the white wire at the junction of `R55` and `R56` (the trace connecting them).
8. Power on the game and connect a smartphone to the **WarpedPinball** WiFi network. Click **Sign In** if prompted.
9. Review the configuration page that appears.
10. Select your home WiFi SSID and password. Choose your game and software version from the dropdown. If not listed, select **GenericSystem11** and contact Warped Pinball.
11. Set a Pinball Admin password only if you want the Admin/Service page protected (it already requires being on your WiFi).
12. Click **Save**, wait one minute, then power off the game.
13. Power on and wait for the IP address to appear on the display (GenericSystem11 will not show one). Enter the IP on any device on the same WiFi—for example `192.168.1.189`.

Enjoy the game and chase new high scores! Enter player names so everyone gets an individual best-score board.

Set adjustment numbers **18**, **19**, **20**, and **21** to zero to prevent the game from awarding credits when initials are entered.

Your kit includes a jumper wire for System 11 boot-up sound board issues and a plastic hex standoff for System 9 installations. Some games mount the main board upright—orientation may differ from photos.

This Warped Pinball product is patent pending.
