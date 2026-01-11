<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">Data East Installation and Use Manual</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>

[Back to All Guides](../index.md)

Indicators, installation steps, WiFi setup, and operational notes for Data East Vector.

## Table of contents

- [How it works](#how-it-works)
- [Indicators and controls](#indicators-and-controls)
- [Disclaimer](#disclaimer)
- [Hardware installation](#hardware-installation)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Operation](#operation)

## How it works

The Data East Vector board installs between the processor chip and the game’s main board, mimicking the RAM chip that stores game settings. Gameplay remains unchanged while the board stores RAM values in permanent memory, eliminating batteries or NVRAM modifications. Installation requires no soldering or permanent changes.

## Indicators and controls

- **WiFi Status LED**
  - Fast blink: AP mode
  - Slow blink: Joining WiFi
  - Solid: WiFi joined and active
- **Boot Button**: Typically unused; reserved for major Raspberry Pi Pico updates.
- **WiFi Configure Button**
  - Hold during power-up
  - Release when the LED flashes to enter setup mode
- **Status LED**: Fast blink indicates an installation fault.

## Disclaimer

Removing and reseating chips carries risk. Work with the game powered off but grounded, discharge static on the metal backplane, and verify sockets and ICs are fully seated. Ensure correct fuse sizes. Warped Pinball offers email support but cannot be liable for damage.

## Hardware installation

1. Remove the main processor (`MC6802`) from the game board and insert it into the Data East Vector socket, confirming pins are straight and fully seated.
2. Insert the supplied pin-strip headers into the main-board processor socket, pressing firmly until fully seated.
3. Place the round-pin chip carrier into the headers, ensuring all pins seat completely.
4. Attach the adhesive standoff to the Data East Vector board with the provided plastic screw, remove the backing, and align the board with the socket. Inspect all corners to confirm proper seating.
5. Clip the white wire with the micro clip to the junction of `R55` and `R56` (either component on the correct side). This synchronizes resets on power-up.

After installation the game operates normally while Data East Vector provides NVRAM service. Additional features require WiFi configuration.

## Connecting to local WiFi

1. Power on the machine; the WiFi status LED blinks fast (AP mode).
2. Join the **Warped Pinball** network from a phone or computer and ignore “no internet” warnings.
3. If a captive portal does not appear, open a browser to reach the configuration page.
4. On the configuration page:
   - Select your WiFi SSID and password.
   - Choose your game from the dropdown or select **GenericDataEast** if not listed.
   - Optionally set an admin password to protect actions such as clearing scores.
   - If the board previously joined a network, its last IP address appears on this screen.
5. Click **Save**, power-cycle the machine, and allow it to reconnect. Slow blinking means it is joining; solid indicates a successful connection.
6. If joining fails (slow blink for several minutes), power down, hold the WiFi setup button, power up, release when any LED blinks rapidly, and repeat setup.

**Pro Tip:** To re-enter configuration mode later, hold the WiFi config button during power-up and release when the LED blinks rapidly.

## IP addresses

- The router assigns an IP address to each Data East Vector device (e.g., `192.168.1.239`).
- Access the machine by entering its IP address in a browser on the same network.
- Machines periodically display their IP address on the game display; note changes if the router reassigns addresses.
- For stability, configure a static IP in your router once the device is visible in the connected devices list.

Example: IP address `192.168.1.189` displayed on a Pinbot machine.

## Operation

- Prevent automatic credit awards during initials entry by setting adjustments `18`, `19`, `20`, and `21` to `0` using the coin-door controls.
- Data East Vector stores all data locally; remote access is limited to devices on the same network.
- Most games display the IP address in attract mode with spaces separating the four numbers.

Have feature ideas? Visit [WarpedPinball.com](https://WarpedPinball.com). This Warped Pinball product is patent pending.
