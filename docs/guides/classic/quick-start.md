<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">Classic (Bally / Stern) WiFi Quick Start</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>

<!-- DRAFT / PLACEHOLDER - content not yet reviewed. Fill in each TODO before publishing. -->

Fast-path instructions for installing the Warped Pinball Vector board on a Bally or
Stern solid-state "classic" machine (AS-2518 / MPU-35 / MPU-200 era).

## Steps

Check out installation videos at [WarpedPinball.com](https://WarpedPinball.com).

1. Power off the pinball machine.
2. Remove the main processor chip from the MPU board and place it into the Vector
   board's socket, matching pin #1 and checking for bent pins.

   <!-- TODO: add chip-location photo -> docs/img/classic/chip_location.png -->

3. Insert the pin strips into the main-board processor socket. Press firmly so each
   pin seats fully.

   <!-- TODO: add pin-strip photo -->

4. Insert the round-pin chip carrier into the socket strips (may be pre-installed on
   your kit).
5. Attach the sticky standoff and screw to the MPU board and peel the backing.
6. Place the Vector board into the main-board socket, confirm all pins are seated,
   and check processor orientation against the original.
7. Inspect / adjust the reset circuit.

   <!-- TODO: document the classic reset-hold requirement (MPU-35 vs MPU-200) -->

8. Power on the game and connect a smartphone to the **WarpedPinball** WiFi network.
   Tap **Sign In** if prompted.
9. On the configuration screen select your home WiFi, enter the password, and pick
   your **game** from the dropdown. Use **Generic** (MPU-35 / Bally-35) or
   **GenericMPU200** if your title is not listed.
10. Save and power-cycle. A green blinking status LED confirms the WiFi connection.

See the [full manual](manual.md) for LED codes, IP display, and operation.

This Warped Pinball product is patent pending.
