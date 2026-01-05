<!-- pdf-download-button:start -->
<a class="pdf-download-button" href="https://raw.githubusercontent.com/wiki/warped-pinball/vector/wiki-pdf/System%2011/System%2011%20Manual.pdf" style="display:inline-block;padding:0.45rem 1.1rem;background:#1f4ed8;color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">Download this page as a PDF</a>
<!-- pdf-download-button:end -->

# System 11 WiFi Module Installation and Use Manual


## How It Works
The SYS11.WiFi circuit board installs between the processor chip and your game’s main board, mimicking the RAM chip that stores game settings. The game continues to run its original software, so gameplay remains unchanged. SYS11.WiFi stores RAM values in on-board permanent memory, eliminating the need for batteries or NVRAM modifications, and it installs without soldering or permanent game changes.

## Indicators and Controls
- **WiFi Status LED**
    - Fast blink: AP mode
    - Slow blink: Joining WiFi
    - Solid: WiFi joined and active
- **Boot Button**
    - Typically unused; reserved for major Raspberry Pi Pico updates
- **WiFi Configure Button**
    - Hold during power-up and release when the LED flashes to enter setup mode
- **Status LED**
    - Fast blink indicates an installation fault

## Disclaimer
Removing and reseating chips carries risk. Work with the game powered off but still grounded, touch the metal backplane to discharge static, and verify that sockets and ICs are fully seated. Ensure correct fuse sizes are installed. Warped Pinball provides email support but cannot be liable for damage to you or your machine.

## Hardware Installation
1. Remove the main processor (MC6802) from the game’s board and insert it into the SYS11.WiFi socket, confirming all pins are straight and fully seated.
2. Insert the supplied pin-strip headers into the main board processor socket, pressing firmly until fully seated.
3. Place the round-pin chip carrier into the headers, again ensuring all pins seat completely.
4. Attach the adhesive standoff to the SYS11.WiFi board with the provided plastic screw, remove the backing, and align the board with the socket. Inspect all corners to confirm proper seating.
5. Clip the white wire with the micro clip to the junction of R55 and R56 (either component is acceptable as long as it is the correct side). This connection synchronizes resets on power-up.

At this point the game operates normally, and SYS11.WiFi provides NVRAM service. Additional features require WiFi configuration.

## Connecting to Local WiFi
1. Power on the machine; the WiFi status LED will blink fast (AP mode).
2. Using a phone or computer, join the WiFi network named **Warped Pinball**. Ignore any “no internet” warnings.
3. If a captive portal screen does not appear automatically, open a browser to reach the configuration page.
4. On the configuration page:
     - Select your local WiFi SSID and enter its password (case-sensitive).
     - Choose your game from the dropdown or select **GenericSystem11** if not listed.
     - Optionally set an admin password to protect functions such as clearing scores.
     - If the board previously joined a network, its last IP address appears on this screen.
5. Click **Save**, power-cycle the machine, and allow the board to reconnect. The WiFi status LED blinks slowly while joining and turns solid once connected.
6. If joining fails (slow blink for several minutes), power down, hold the WiFi setup button, power up, release when any LED blinks rapidly, and repeat the setup.

**Pro Tip:** To re-enter configuration mode later, hold the WiFi config button during power-up and release when the LED blinks rapidly.

## IP Addresses
- The router assigns an IP address to each SYS11.WiFi device (e.g., `192.168.1.239`).
- Access the machine by entering its IP address in a browser on the same network.
- Machines periodically display their IP address on the game display; note changes if the router reassigns addresses.
- For stability, configure a static IP in your router once the device is visible in the connected devices list.

*Example: IP address `192.168.1.189` displayed on a Pinbot machine.*

## Operation
- Prevent automatic credit awards during initials entry by setting adjustments 18, 19, 20, and 21 to `0` using the coin-door controls.
- SYS11.WiFi stores all data locally; remote access is limited to devices on the same network.
- Most games display the IP address in attract mode with spaces separating the four numbers.

Have feature ideas? Visit [WarpedPinball.com](https://WarpedPinball.com).
*Warped Pinball product is patent pending.*
