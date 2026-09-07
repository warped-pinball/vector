<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">Classic WiFi App Note: New Game ROM Profile</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>

<!-- DRAFT / PLACEHOLDER - content not yet reviewed. Fill in each TODO before publishing. -->

Collect memory images so a new Bally / Stern classic title can be profiled for
scoring and leaderboard support.

## Process

Install the Vector board and select **Generic** (MPU-35 / Bally-35) or
**GenericMPU200** for the game name to match your board. Connect via WiFi so you can
use the browser interface. Find the board's IP by:

- Looking it up in your router's connected-devices list.
- Re-entering WiFi setup mode (hold the button while powering up until it blinks
  fast) and reading the IP at the bottom of the AP screen.
- Linking from another Warped Pinball game already on the network.

Once connected, capture the memory images needed to build a profile. `GameName` can
be an abbreviation.

1. Factory reset the game if needed.
2. Download a baseline memory file from the Admin page: `GameName_Baseline.txt`.
3. Start a single-player game; leave ball #1 in the shooter lane. Download
   `GameName_1player_ball1.txt`.
4. Play ball #1, pause on ball #2, include the player-1 score in the name:
   `GameName_1player_ball2_yyyyy.txt`.
5. Start a multi-player game and capture two files with different balls, players up,
   and scores, e.g. `GameName_4player_ball2_player3up_12000_8000_25000_0.txt`.
6. Note the machine high score (and initials, if the title stores them), then
   download `GameName_HighScore_ABC150000.txt`.
7. If the title shows a custom message / IP area on the displays, capture
   `GameName_Message.txt`.
8. Email all files plus the game software / ROM revision to
   [roms@WarpedPinball.com](mailto:roms@WarpedPinball.com).

<!-- TODO: confirm the exact capture list for classics. Unlike WPC there is:
     - one machine high score, usually no initials
     - no adjustment checksum step
     - InPlay Type 30 (digit-per-byte) vs Type 31/32 (packed BCD) - note which
       ROM families use which so the profiler knows what to look for -->

When a profile is ready it is added to a firmware update; click **Update** on the
Admin page, then verify high score recording and (if supported) IP display.

This Warped Pinball product is patent pending.
