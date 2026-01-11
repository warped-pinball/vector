<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
   <h1 style="margin: 0;">System 9 WiFi Module Installation and Use Manual</h1>
   <button onclick="window.print()" style="white-space: nowrap;">
      <span aria-hidden="true">🖨️</span> Print This Guide
   </button>
</div>



Setup and operation details for SYS9.WiFi.

## Table of contents

- [Supported games](#supported-games)
- [How it works](#how-it-works)
- [Indicators and controls](#indicators-and-controls)
- [Disclaimer](#disclaimer)
- [Hardware installation](#hardware-installation)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Operation](#operation)
- [Support](#support)

## Supported games

- Comet
- Space Shuttle
- Sorcerer

## How it works

The SYS9.WiFi board installs between the processor chip and the game’s main board to emulate the RAM that stores settings. Gameplay runs on the original software, while the board stores RAM values in permanent memory, eliminating batteries or NVRAM mods. The SYS9 hardware matches the SYS11 board but runs firmware tailored to System 9 titles.

## Indicators and controls

**Components**

- **WiFi Status LED**: Shows the current network state
- **Status LED**: Indicates installation status
- **Boot Button**: Used only for major firmware updates on the Raspberry Pi Pico
- **WiFi Configure Button**: Puts the board into setup mode

**WiFi Status LED**

- **Fast blink** – Access Point (AP) mode
- **Slow blink** – Joining WiFi
- **Solid on** – WiFi connected and active

**Status LED**

- **Fast blink** – Installation fault detected

**Boot Button**

Not typically used; reserved for loading new firmware on the Raspberry Pi Pico.

**WiFi Configure Button**

1. Hold during power-up.
2. Release when any LED flashes rapidly.
3. The board enters WiFi setup mode (AP mode).

## Disclaimer

Pulling chips out of classic games carries inherent risk. If you have never re-seated chips, seek help from someone experienced. Work with the game powered off but plugged in for grounding, discharge static on the metal backplane, double-check every pin for full seating, and confirm fuse ratings.

Warped Pinball offers email support and will assist when possible, but cannot be liable for damage to persons or machines.

## Hardware installation

1. **Remove the main processor**
   - Locate the MC6802 processor on the main board.
   - Carefully remove the chip and inspect pins for alignment.
2. **Insert the processor into SYS9.WiFi**
   - Place the MC6802 into the SYS9.WiFi socket.
   - Ensure pins are straight and press evenly until fully seated.
3. **Install pin strip headers**
   - Insert the provided pin strip headers into the main-board processor socket.
   - Press firmly on sections of 3–4 pins until fully seated.
4. **Add the round pin chip carrier**
   - Place the round pin chip carrier on top of the headers.
   - Press down around the carrier to seat all pins securely.
5. **Mount the SYS9.WiFi board**
   - Attach the standoff using the plastic screw.
   - Align the board with the socket, verify pin alignment, and press firmly until seated.
6. **Connect the reset wire**
   - Attach the white micro clip to the junction of `R5` and `R4` (location varies by board orientation).
   - This synchronizes resets during power-up; expect a few extra seconds at startup.
   - This connection is mandatory for proper operation.

After installation the game operates normally and the board provides NVRAM service. Configure WiFi to enable advanced features.

## Connecting to local WiFi

1. Power on the pinball machine. The WiFi status LED blinks rapidly (AP mode).
2. On a phone or computer, join the **Warped Pinball** network and ignore no-internet warnings.
3. When prompted, tap **Sign In** or open a browser to reach the configuration page.

On the configuration page:

- Select your local WiFi SSID.
- Enter the WiFi password (case-sensitive).
- Choose your game from the dropdown; if not listed, select **Generic System 11** (incorrect selection can cause erratic behavior).
- Optionally set an Admin Password to protect actions such as erasing scores.
- If the board previously joined a network, its IP address appears at the bottom.
- Click **Save** and power-cycle the game.

On power-up the WiFi Status LED blinks slowly while searching and turns solid when connected. If it keeps blinking slowly, power down, hold the WiFi Configure button, power up, and release when any LED blinks rapidly.

## IP addresses

- Your router assigns an IP address to each machine (e.g., `192.168.1.239`).
- Access the machine by entering its IP in a browser on the same network and bookmark it.
- Routers may change assignments; SYS9.WiFi periodically displays the current IP on the game display.
- Set a static IP in your router once the device is connected for stability.

Example display: IP address `188.168.1.115` shown on a Comet machine.

## Operation

- All data stays local on the board; nothing is pushed to the internet.
- Access the interface only from devices on the same network via the assigned IP.
- System 9 games display the IP address in place of high scores during attract mode.

Warped Pinball product is patent pending.

## Support

Need help or have feature ideas? Visit [WarpedPinball.com](https://WarpedPinball.com).
