<!-- pdf-download-button:start -->
<a class="pdf-download-button" href="https://raw.githubusercontent.com/wiki/warped-pinball/vector/wiki-pdf/WPC/WPC%20Manual.pdf" style="display:inline-block;padding:0.45rem 1.1rem;background:#1f4ed8;color:#fff;text-decoration:none;border-radius:999px;font-weight:600;">Download this page as a PDF</a>
<!-- pdf-download-button:end -->

# System WPC WiFi Module Installation and Use Manual

## How It Works

The circuit board is installed between the processor chip and your game's main circuit board. In this position it can act just like the RAM chip on the board where game settings are stored. Your game continues to run the same software on the same processor, so there is no change in gameplay.

`SYSWPC.Wifi` stores RAM values in onboard permanent memory, removing the need for batteries or NVRAM modifications. Installation requires **no** permanent modification to the game and installs without soldering.

## Indicators and Controls

- **WiFi Status LED**
    - *Fast Blink*: AP mode
    - *Slow Blink*: Joining WiFi
    - *Solid On*: WiFi joined and active
- **WiFi Configure Button**
    - Hold during power-up
    - Release when LED flashes for setup mode
- **Status LED**
    - Fast blink indicates installation fault

## Disclaimer

> While it is less risky than soldering, pulling chips out of classic games does have some risks. While we make every effort to make this an easy and safe process, damage to your game is possible and we cannot be responsible if something goes wrong. If you have never pulled and re-seated chips in a board like this we encourage you to find someone who has and offer them some pizza to come help.
>
> Some things to watch for: static electricity can damage circuits. When working on your game turn it off but leave it plugged in so it has a ground connection. Also not a bad idea to touch the metal backplane before you touch electronics—just to make sure that charge you got walking across the carpet is gone. Partially seated sockets and ICs cause crazy problems—look at all the pins at each assembly step to make sure they are pushed in all the way. It is possible for one corner of a socket or IC to be up when the other corner looks ok. As always be sure your game has the correct size fuses installed.
>
> We offer email support and will do anything we can to help you enjoy Warped Pinball accessories. We cannot however be liable for any damage to yourself or machine.

## Hardware Installation

`SYS WPC.Wifi` will be installed in the socket where your game’s main processor currently resides.

1. Carefully remove the processor (`MC6809`) and place it into the socket on the `SYS WPC.Wifi` board. Check that all pins are straight before inserting and press firmly until the chip is fully seated.
2. To make mounting easier and the connections more reliable, use the accessory connectors:
     - Insert the pin strip headers into each side of the main board processor socket, pressing 3–4 pins at a time until fully seated.
     - Place the round pin chip carrier on top of the pin strip headers and press each pin firmly until seated.
3. (Optional) Attach the adhesive standoff to the Warped Pinball board using the included plastic screw. Remove the backing so it adheres to the top of a neighboring chip when positioned.
4. Insert the `SYS WPC.Wifi` board into the socket on the main board. Align all pins, press firmly, and confirm each corner is seated.

### Supported Games

- **Early WPC**: Black Rose, Bram Stoker’s Dracula, Creature from the Black Lagoon, Demolition Man, Doctor Who, Fish Tales, Funhouse, Gilligan’s Island, Harley-Davidson, Hurricane, Indiana Jones, Judge Dredd, Machine: Bride of Pinbot, Party Zone, Popeye Saves the Earth, Star Trek: TNG, Terminator 2, The Addams Family I & II, The Getaway: High Speed II, Twilight Zone, White Water
- **WPC-S & WPC-95**: Corvette, Dirty Harry, Indianapolis 500, JackBot, Johnny Mnemonic, No Fear: Dangerous Sports, Red and Ted’s Road Show, The Flintstones, The Shadow, Theatre of Magic, WHO Dunnit, World Cup Soccer
- **WPC-95 (continued)**: Attack from Mars, Cactus Canyon, Cirqus Voltaire, Congo, Junk Yard, Medieval Madness, Monster Bash, NBA Fastbreak, No Good Gofers, Safe Cracker, Scared Stiff, Tales of the Arabian Nights, The Champion Pub

5. Connect the white wire with the attached micro clip to the main board reset circuit at `R22`. This synchronizes resets on power-up and is **mandatory**. Push the end of the handle to extend the clip and hook it as indicated.

Once connected, your game will operate normally while the `SYS WPC.Wifi` board provides NVRAM service. Configure WiFi to access advanced scoring, tournament, and other features.

## Connecting to Local WiFi

1. Power up the pinball machine; the WiFi status LED should blink fast.
2. Using a phone or computer, open WiFi settings and join the **Warped Pinball** network. A warning about no internet is expected.
3. When prompted, tap **Sign In** or open a browser to reach the configuration screen.

### Configuration Screen

- Select your local WiFi **SSID** and enter the corresponding password (case sensitive).
- Choose your **game** from the dropdown (use `GenericWPC` if not listed; incorrect selection can cause erratic behavior).
- Optionally set an **Admin Password** to protect actions like erasing scores and leaderboards.
- If the board previously joined a network, the assigned IP address is shown at the bottom.

Click **Save**. The WiFi status LED will stop blinking. Power cycle the game to apply settings. On the next boot:
- Slow blinking indicates the unit is locating the network.
- Solid LED confirms a successful connection.
- Slow blinking for several minutes means the join failed—power down, hold the WiFi setup button while powering up, release when the LED blinks fast, and repeat the pairing process.

**Pro Tip:** To re-enter configuration mode later, hold the WiFi config button during power-up until the LED blinks rapidly.

## IP Addresses

Each machine obtains an IP address from your router (e.g., `192.168.1.79`). Access the board by entering the IP in a browser. Save a bookmark for convenience. Router DHCP assignments can change over time; the board periodically displays the current IP on the machine display. For a fixed IP, log into your router, locate the device, and mark the entry as **static**.

> *Example*: IP address `192.168.1.79` displaying on the DMD.
> Have a color Pin2DMD? Use the buttons on the display to set it to **Williams/Bally Mode**.

## Operation

- Navigation buttons are located in the upper-right corner.
- Tournament and personal best scoreboards are accessible via the banner.
- Enter player full names under **Players**.

**Features video:** <https://youtu.be/eGVe5E9X-2I>

Have a great idea for a new feature? Contact us online at **WarpedPinball.com**.
