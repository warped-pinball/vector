<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">WPC Vector Installation and Use Manual</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>



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

<!-- Two-column layout using a Markdown table -->

| ![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_Board_Controls.png) | WiFi Status LED <br>-Fast blink: AP Mode <br>-Slow Blink: Joining WiFi<br>-Solid ON: WiFi joined<br><br>WiFi Configure Button: Hold during power up and release when LED flashes for AP setup mode<br><br>Status LED<br>-fast blink: installation fault |
| --- | --- |

## Disclaimer

Removing classic game chips carries risk. Work with the game powered off but still grounded, discharge static before touching electronics, and double-check that sockets and ICs are fully seated. Incorrect fuse sizes or partially seated components can damage the machine. Warped Pinball provides email support but cannot be liable for damage.

## Supported Games

| Installation picture | WPC version | Titles |
| --- | --- | --- |
| ![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_installed.jpg) | Williams/Bally WPC | Black Rose<br>Bram Stoker's Dracula<br>Creature from the Black Lagoon<br>Demolition Man<br>Doctor Who<br>Fish Tales<br>Funhouse<br>Gilligan's Island<br>Harley-Davidson<br>Hurricane<br>Indiana Jones<br>Judge Dredd<br>Machine: Bride of Pinbot<br>Party Zone<br>Popeye Saves the Earth<br>Star Trek: TNG<br>Terminator 2<br>The Addams Family I/II<br>The Getaway: High Speed II<br>Twilight Zone<br>White Water |
| ![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_S_installed.jpg) | Williams/Bally WPC-S | Corvette<br>Dirty Harry<br>Indianapolis 500<br>JackBot<br>Johnny Mnemonic<br>No Fear: Dangerous Sports<br>Red and Ted's Road Show<br>The Flintstones<br>The Shadow<br>Theatre of Magic<br>WHO Dunnit<br>World Cup Soccer |
| ![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_95_installed.jpg) | Midway/Williams WPC-95 | Attack from Mars<br>Cactus Canyon<br>Cirqus Voltaire<br>Congo<br>Junk Yard<br>Medieval Madness<br>Monster Bash<br>NBA Fastbreak<br>No Good Gofers<br>Safe Cracker<br>Scared Stiff<br>Tales of the Arabian Nights<br>The Champion Pub |
| ![Williams/Bally WPC RD install photo](../../img/wpc/manual/WPC_RD_installed.jpg) | WPC | Rotten Dog<br>aftermarket<br>Board<br>Installation |

## Hardware installation

1. Carefully remove the processor (`MC6809`) and place it into the socket on the Vector board according to pin #1 designation. Verify pins are straight and fully seated. Chip locations are identified in these pictures (depending on your game model) <br><br>

![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_chip_location.png)

![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_S_chip_location.png)

![Williams/Bally WPC install photo](../../img/wpc/manual/WPC_95_chip_location.png)

Throughout the installation pay attention to pin #1 alignment:

<img src="../../img/wpc/manual/pin_one.png" alt="Pin one Photo" width="220">

2. To improve mounting and connection reliability, insert the pin-strip headers into each side of the main-board processor socket. Press 3–4 pins at a time until fully seated. 

<img src="../../img/wpc/manual/pin_strip.jpg" alt="Pin strip Photo" width="180">

3. Place the 40 pin socket into the pin strip headers (on some kit this header is already attached to the circuit board, you can skip this step) 


<img src="../../img/wpc/manual/socket.jpg" alt="socket Photo" width="180">

4. (Optional) Attach the adhesive standoff to the Vector board with the included plastic screw so it can adhere to a neighboring chip. <br>

<img src="../../img/wpc/manual/standoff.png" alt="Pin standoff Photo" width="180">

5. Insert the Vector board into the socket on the main board. Align all pins, press, and confirm each corner is seated. Pay attention to pin #1 alignment throughout this installation.




| WPC Clip Location | WPC-S Clip Location |
| :---: | :---: |
| ![WPC Clip](../../img/wpc/manual/WPC_clip.jpg)<br>WPC | ![WPC-S Clip](../../img/wpc/manual/WPC_S_clip.jpg)<br>WPC-S |

| WPC-95 Clip Location | Rotten Dog Clip Location |
| :---: | :---: |
| ![WPC-95 Clip](../../img/wpc/manual/WPC_95_clip.jpg)<br>WPC-95 | ![Rotten Dog Clip](../../img/wpc/manual/WPC_RD_clip.jpg)<br>Rotten Dog |


After connection the game operates normally while the Vector board provides NVRAM service. Configure WiFi to access advanced scoring, tournament, and other features.

## Connecting to local WiFi
1. Power up the pinball machine; the WiFi status LED should blink fast.
2. On a phone or computer, open WiFi settings and join the **Warped Pinball** network. A no-internet warning is expected.

<p align="center">
  <img src="../../img/wpc/manual/WPC-Installation-manual_AP_setup_screen.png" alt="Pin standoff Photo" width="220">
</p>

3. When prompted, tap **Sign In** or open a browser to reach the configuration screen.


<p align="center">
  <img src="../../img/wpc/manual/WPC-Installation-manual_sign_in_button.png" alt="Pin standoff Photo" width="220">
</p>

4. On the configuration screen:
   - Select your local WiFi **SSID** and enter the password (case sensitive).
   - Choose your **game** from the dropdown (use `GenericWPC` if not listed; incorrect selection can cause erratic behavior).
   - Optionally set an **Admin Password** to protect actions like erasing scores and leaderboards.
   - If Vector previously joined a network, the assigned IP address is shown at the bottom.


<p align="center">
  <img src="../../img/wpc/manual/WPC-Installation-manual_AP_setup_screen.png" alt="Pin standoff Photo" width="220">
</p>

5. Click **Save**. The WiFi status LED will stop blinking. Power-cycle the game to apply settings. On the next boot:
   - Slow blinking indicates the unit is locating the network.
   - Solid LED confirms a successful connection.
   - Slow blinking for several minutes means the join failed—power down, hold the WiFi setup button while powering up, release when the LED blinks fast, and repeat pairing.

**Pro Tip:** To re-enter configuration mode later, hold the WiFi config button during power-up until the LED blinks rapidly.

## IP addresses

Each machine receives an IP address from your router (for example `192.168.1.79`). Access Vector by entering the IP in a browser and save it as a bookmark. Router DHCP assignments can change; the Vector board periodically displays the current IP on the machine display. To keep the same address, log into your router, locate the device, and mark the entry as **static**.


<p align="center">
  <img src="../../img/wpc/manual/WPC-Installation-manual_IP_on_DMD.png" alt="Pin standoff Photo" width="420">
</p>

Have a color Pin2DMD?   Use the buttons on the back of the display to set it to **Williams/Bally Mode**.

## Operation

- Navigation buttons are in the upper-right corner.
- Tournament and personal best scoreboards are accessible via the banner.
- Enter player full names under **Players**.


<p align="center">
  <img src="../../img/wpc/manual/WPC-Installation-manual_vector_screen_main.png" alt="Pin standoff Photo">
</p>

Watch the [features video](https://youtu.be/eGVe5E9X-2I) and send ideas via [WarpedPinball.com](https://WarpedPinball.com).
