<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">Classic (Bally / Stern) Vector Installation and Use Manual</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>

<!-- DRAFT / PLACEHOLDER - content not yet reviewed. Fill in each TODO before publishing. -->

How the Vector board installs, what the LEDs mean, and how to bring a Bally or Stern
solid-state classic machine online.

## Table of contents

- [How it works](#how-it-works)
- [LED codes](#led-codes)
- [Disclaimer](#disclaimer)
- [Supported games](#supported-games)
- [Hardware installation](#hardware-installation)
- [Connecting to local WiFi](#connecting-to-local-wifi)
- [IP addresses](#ip-addresses)
- [Operation](#operation)

## How it works

Vector sits between the processor chip and the game's main board so it can act like
the RAM chip where settings and scores are stored. Gameplay continues unchanged: the
same ROM runs on the same processor. Vector mirrors RAM into on-board permanent
memory. Installation requires no permanent modification or soldering.

<!-- TODO: note anything classic-specific here:
     - 6810 volatile RAM (0x000-0x07F) vs 5101 battery-backed nibble RAM (0x100-0x1FF)
     - MPU-200 boards have full-byte RAM at 0x100-0x1FF (handled by the MPU200 mode switch)
     - address bus is A0-A8 only (no data-bus intercept for the fault check) -->

## LED codes

The Status LED uses color combinations to indicate system status and faults. Each
fault code is two color blinks separated by a brief pause.

### Normal Operation
| LED Pattern | Status |
| --- | --- |
| Yellow-Yellow (dim) | Trying to join WiFi at startup |
| Green-Green (dim) | WiFi connected, all systems OK |
| Purple-Purple (dim) | AP mode - join with your phone |

### Hardware Faults (First blink: RED)
| LED Pattern | Code | Description |
| --- | --- | --- |
| Red-Yellow | HDWR01 | Early Bus Activity (reset hold not working) |
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

**Note:** Multiple faults are displayed in sequence with a pause (black) between each code.

## Disclaimer

Removing classic game chips carries risk. Work with the game powered off but still
grounded, discharge static before touching electronics, and double-check that sockets
and ICs are fully seated. Incorrect fuse sizes or partially seated components can
damage the machine. Warped Pinball provides email support but cannot be liable for
damage.

## Supported games

<!-- TODO: keep this table in sync with src/classic/config/*.json -->

| System | Titles |
| --- | --- |
| Bally MPU-35 (AS-2518-35) | Supersonic<br>_(generic profile: **Generic**)_ |
| Bally / Stern MPU-200 | Split Second<br>_(generic profile: **GenericMPU200**)_ |

If your title is not listed, select **Generic** or **GenericMPU200** to match your
board. See [Add a ROM profile](add-rom.md) to help profile a new title.

## Hardware installation

<!-- TODO: full step-by-step with photos under docs/img/classic/ -->

1. Remove the MPU processor and seat it in the Vector board socket, pin #1 aligned.
2. Insert the pin-strip headers into each side of the main-board processor socket.
3. Seat the 40-pin socket into the pin strips; press firmly all the way around.
4. Attach the adhesive standoff to the Vector board with the plastic screw.
5. Insert the Vector board into the main-board socket; confirm every corner is seated.
6. Address the reset circuit as required for your board revision. <!-- TODO -->

After connection the game operates normally while Vector provides NVRAM service.
Configure WiFi to access scoring, tournament, and leaderboard features.

## Connecting to local WiFi

1. Power up the machine; the WiFi status LED starts Yellow then flashes Purple.
2. On a phone or computer, join the **Warped Pinball** network (a no-internet warning
   is expected).
3. When prompted, tap **Sign In** or open a browser to reach the configuration screen.
4. On the configuration screen:
   - Select your local WiFi **SSID** and enter the password (case sensitive).
   - Choose your **game** from the dropdown (use **Generic** / **GenericMPU200** if
     not listed; an incorrect selection can cause erratic behavior).
   - Optionally set an **Admin Password** to protect actions like erasing scores.
5. Click **Save** and power-cycle the game. Yellow blinking = locating network;
   Green blinking = connected.

## IP addresses

Each machine receives an IP address from your router (for example `192.168.1.79`).
Enter it in a browser and bookmark it. Router DHCP assignments can change; to keep the
same address, mark the entry **static** in your router.

<!-- TODO: confirm which classic titles can show the IP on the score displays
     (DisplayMessage Type 30 - e.g. Supersonic) and how it is formatted. -->

## Operation

- Navigation buttons are in the upper-right corner of the web UI.
- Tournament and personal best scoreboards are on the banner.
- Enter player full names under **Players**.
- The Admin panel handles configuration save/restore and software updates.

<!-- TODO: note classic limitations - single machine high score, no initials,
     no score write-back to the machine. -->

Send ideas via [WarpedPinball.com](https://WarpedPinball.com).
