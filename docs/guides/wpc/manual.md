# WPC Vector Installation and Use Manual

Back to [all guides](../index.md).

How the Vector board installs, what the LEDs mean, and how to bring a classic Williams/Bally WPC machine online.

## Table of contents

- [How it works](#how-it-works)
- [Indicators and controls](#indicators-and-controls)
- [Disclaimer](#disclaimer)
- [Hardware installation](#hardware-installation)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Operation](#operation)

## How it works

Vector sits between the processor chip and the game’s main board so it can act like the RAM chip where settings are stored. Gameplay continues unchanged. the same ROM runs on the same processor. Vector stores RAM values in on-board permanent memory. Installation requires no permanent modification or soldering.


<table>
  <tr>
    <td style="vertical-align: top; padding-right: 16px;">
      <img src="../../img/wpc/manual/WPC-Installation-manual_page_1_2.png" alt="img1" width="350">
    </td>
    <td style="vertical-align: top;">
      <h3>WiFi Status LED</h3>
      <ul>
        <li><strong>Fast blink</strong>: AP mode</li>
        <li><strong>Slow blink</strong>: joining WiFi</li>
        <li><strong>Solid on</strong>: WiFi joined and active</li>
      </ul>
      <h3>WiFi Configure Button</h3>
      <p>Hold during power-up and release when LED flashes for setup mode.</p>
      <h3>Status LED</h3>
      <ul>
        <li><strong>Fast blink</strong>: Installation fault</li>
      </ul>
    </td>
  </tr>
</table>

## Disclaimer

Removing classic game chips carries risk. Work with the game powered off but still grounded, discharge static before touching electronics, and double-check that sockets and ICs are fully seated. Incorrect fuse sizes or partially seated components can damage the machine. Warped Pinball provides email support but cannot be liable for damage.

## Supported Games

| Installation picture | WPC version | Titles |
| --- | --- | --- |
| <img src="../../img/wpc/manual/WPC-Installation-manual_page_8_1.png" alt="Williams/Bally WPC install photo" width="280"> | Williams/Bally WPC | Black Rose<br>Bram Stoker's Dracula<br>Creature from the Black Lagoon<br>Demolition Man<br>Doctor Who<br>Fish Tales<br>Funhouse<br>Gilligan's Island<br>Harley-Davidson<br>Hurricane<br>Indiana Jones<br>Judge Dredd<br>Machine: Bride of Pinbot<br>Party Zone<br>Popeye Saves the Earth<br>Star Trek: TNG<br>Terminator 2<br>The Addams Family I/II<br>The Getaway: High Speed II<br>Twilight Zone<br>White Water |
| <img src="https://github.com/user-attachments/assets/2888dac3-a575-4b9d-b037-1703e4dea2a0" alt="Williams/Bally WPC-95 install photo" width="280"> | Williams/Bally WPC-95 | Corvette<br>Dirty Harry<br>Indianapolis 500<br>JackBot<br>Johnny Mnemonic<br>No Fear: Dangerous Sports<br>Red and Ted's Road Show<br>The Flintstones<br>The Shadow<br>Theatre of Magic<br>WHO Dunnit<br>World Cup Soccer |
| <img src="https://github.com/user-attachments/assets/9b90fb67-893e-4b25-b5bf-bad0944858ac" alt="Midway/Williams WPC-95 install photo" width="280"> | Midway/Williams WPC-95 | Attack from Mars<br>Cactus Canyon<br>Cirqus Voltaire<br>Congo<br>Junk Yard<br>Medieval Madness<br>Monster Bash<br>NBA Fastbreak<br>No Good Gofers<br>Safe Cracker<br>Scared Stiff<br>Tales of the Arabian Nights<br>The Champion Pub |

## Hardware installation

1. Carefully remove the processor (`MC6809`) and place it into the socket on the Vector board. Verify pins are straight and fully seated.
2. To improve mounting and connection reliability, insert the pin-strip headers into each side of the main-board processor socket. Press 3–4 pins at a time until fully seated, then place the round-pin chip carrier on top and press each pin firmly.
3. (Optional) Attach the adhesive standoff to the Vector board with the included plastic screw so it can adhere to a neighboring chip.
4. Insert the Vector board into the socket on the main board. Align all pins, press firmly, and confirm each corner is seated.



Connect the white wire with the attached micro clip to the main board reset circuit at `R22`. This synchronizes resets on power-up and is **mandatory**. Push the end of the handle to extend the clip and hook it as indicated.

After connection the game operates normally while the Vector board provides NVRAM service. Configure WiFi to access advanced scoring, tournament, and other features.

## Connecting to local WiFi

1. Power up the pinball machine; the WiFi status LED should blink fast.
2. On a phone or computer, open WiFi settings and join the **Warped Pinball** network. A no-internet warning is expected.
3. When prompted, tap **Sign In** or open a browser to reach the configuration screen.
4. On the configuration screen:
   - Select your local WiFi **SSID** and enter the password (case sensitive).
   - Choose your **game** from the dropdown (use `GenericWPC` if not listed; incorrect selection can cause erratic behavior).
   - Optionally set an **Admin Password** to protect actions like erasing scores and leaderboards.
   - If Vector previously joined a network, the assigned IP address is shown at the bottom.
5. Click **Save**. The WiFi status LED will stop blinking. Power-cycle the game to apply settings. On the next boot:
   - Slow blinking indicates the unit is locating the network.
   - Solid LED confirms a successful connection.
   - Slow blinking for several minutes means the join failed—power down, hold the WiFi setup button while powering up, release when the LED blinks fast, and repeat pairing.

**Pro Tip:** To re-enter configuration mode later, hold the WiFi config button during power-up until the LED blinks rapidly.

## IP addresses

Each machine receives an IP address from your router (for example `192.168.1.79`). Access Vector by entering the IP in a browser and save it as a bookmark. Router DHCP assignments can change; the Vector board periodically displays the current IP on the machine display. To keep the same address, log into your router, locate the device, and mark the entry as **static**.

Have a color Pin2DMD? Use the buttons on the display to set it to **Williams/Bally Mode**.

## Operation

- Navigation buttons are in the upper-right corner.
- Tournament and personal best scoreboards are accessible via the banner.
- Enter player full names under **Players**.

Watch the [features video](https://youtu.be/eGVe5E9X-2I) and send ideas via [WarpedPinball.com](https://WarpedPinball.com).
