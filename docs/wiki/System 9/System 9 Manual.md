<!-- pdf-download-button:start -->
<a class="pdf-download-button" href="https://raw.githubusercontent.com/wiki/warped-pinball/vector/wiki-pdf/System%209/System%209%20Manual.pdf" style="display:inline-block;padding:0.45rem 1.1rem;background:#1f4ed8;color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">Download this page as a PDF</a>
<!-- pdf-download-button:end -->

# System 9 WiFi Module Installation and Use Manual

## Supported Games
- Comet
- Space Shuttle
- Sorcerer

---

## How It Works
The SYS9.WiFi circuit board installs between the processor chip and your game's main circuit board. In this position it emulates the on-board RAM chip that stores game settings. Because your game continues to run the original software on the same processor, gameplay remains unchanged.

SYS9.WiFi stores RAM values in on-board permanent memory, eliminating the need for batteries or NVRAM modifications. Any RAM chip already installed on the main board can remain in place. Installation requires no permanent modification or soldering. The SYS9 circuit board shares hardware with the SYS11 version but runs firmware tailored to System 9 games.

---

## Indicators and Controls

| Component               | Purpose                                                         |
|-------------------------|-----------------------------------------------------------------|
| WiFi Status LED         | Shows the current network state                                 |
| Status LED              | Indicates installation status                                   |
| Boot Button             | Used only for major firmware updates on the Raspberry Pi Pico   |
| WiFi Configure Button   | Puts the board into setup mode                                  |

### WiFi Status LED
- **Fast blink** – Access Point (AP) mode
- **Slow blink** – Joining WiFi
- **Solid on** – WiFi connected and active

### Status LED
- **Fast blink** – Installation fault detected

### Boot Button
- Not typically used; reserved for loading new firmware on the Raspberry Pi Pico.

### WiFi Configure Button
1. Hold during power-up.
2. Release when any LED flashes rapidly.
3. Board enters WiFi setup mode (AP mode).

---

## Disclaimer
Pulling chips out of classic games carries inherent risk. While this process is safer than soldering, damage is still possible. Proceed at your own risk. If you have never removed and re-seated chips, seek assistance from someone experienced.

**Safety tips:**
- Leave the game plugged in (power off) to maintain a ground connection.
- Discharge static by touching the metal backplane before handling electronics.
- After each assembly step, verify that every pin is fully seated; partially seated sockets cause erratic behavior.
- Confirm that all fuses are the correct rating.

Warped Pinball offers email support and will assist when possible, but cannot be liable for damage to persons or machines. Installation and use are undertaken at your own risk.

---

## Hardware Installation

1. **Remove the main processor**
    - Locate the MC6802 processor on your game's main board (see _Location of main processor_).
    - Carefully remove the chip and inspect the pins for alignment.

2. **Insert the processor into SYS9.WiFi**
    - Place the MC6802 into the SYS9.WiFi socket.
    - Ensure all pins are straight and press evenly until fully seated.

3. **Install pin strip headers**
    - Insert the provided pin strip headers into the main board processor socket.
    - Press firmly on sections of 3–4 pins until each pin is fully seated.

4. **Add the round pin chip carrier**
    - Place the round pin chip carrier on top of the pin strip headers.
    - Press down around the carrier to seat all pins securely.

5. **Mount the SYS9.WiFi board**
    - Attach the standoff to the Warped Pinball board using the plastic screw.
    - Align the board with the socket, verify pin alignment, and press firmly until seated.

6. **Connect the reset wire**
    - Attach the white wire with micro clip to the junction of R5 and R4 on the main board (location may vary by board orientation).
    - The board synchronizes resets during power-up; the game will take a few extra seconds to start.
    - This connection is mandatory for proper operation.

At this stage the game operates as normal and the SYS9.WiFi board provides nvRam service. Additional features (advanced scoring, tournaments, etc.) require WiFi configuration.

---

## Connecting to Local WiFi

1. Power on the pinball machine. The WiFi status LED blinks rapidly (AP mode).
2. On a phone or computer, open WiFi settings and connect to the network named **Warped Pinball**. A no-internet warning is normal.
3. When prompted, tap **Sign In** or open a browser; the configuration page should appear.

**Configuration steps:**
- Select your local WiFi SSID from the list.
- Enter the corresponding WiFi password (case-sensitive).
- Choose your game from the dropdown. If not listed, select **Generic System 11**. Incorrect game selection can cause erratic behavior.
- Optionally set an Admin Password to protect functions such as erasing scores.
- If the board previously joined a network, its assigned IP address appears at the bottom of the screen.
- Click **Save**.

SYS9.WiFi stores the WiFi credentials and automatically reconnects on subsequent power cycles. After saving, power the game off and back on to apply the settings.

**Reconnection behavior:**
- On power-up, the WiFi Status LED blinks slowly while searching.
- When connected, the LED turns solid. Failure to connect within several minutes leaves the LED blinking slowly.
- To reset WiFi settings, power down, hold the WiFi Configure button, power up, and release when any LED blinks rapidly.

---

## IP Addresses

- Your router assigns an IP address to each machine. SYS9.WiFi cannot control the assigned address.
- IP addresses have four octets (e.g., `192.168.1.239`).
- Access the machine by entering its IP address in a browser on the same network. Bookmark the address for convenience.
- Routers may change IP assignments over time. SYS9.WiFi periodically displays the current IP address on the game’s display—watch for updates.
- For stability, set a static IP in your router’s admin interface once the device is connected.

_Example display:_ IP address `188.168.1.115` shown on a Comet machine.

---

## Operation

- Warped Pinball stores all data locally on the board; no information is pushed to the internet.
- Access the machine only from devices on the same local network by browsing to the assigned IP address.
- By default, System 9 games display the IP address in place of high scores. Watch the attract mode cycle to view it.

_(Warped Pinball product is patent pending.)_

---

## Support
Need help or have feature ideas? Visit [WarpedPinball.com](https://WarpedPinball.com).
