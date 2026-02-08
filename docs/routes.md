# Vector HTTP API

Generated automatically from `src/common/backend.py`. Use this page as the landing pad for connectivity guides and endpoint documentation.

## Quick links

- [Main repository](https://github.com/warped-pinball/vector)
- [Latest release](https://github.com/warped-pinball/vector/releases/latest)
- [WarpedPinball.com](https://warpedpinball.com)
- [Live demo](https://vector.doze.dev)

## Connectivity guides

- [Authentication](authentication.md)
- [Network access](network.md)
- [Peer discovery](discovery.md)
- [USB transport](usb.md)

## Routes & endpoints

Jump directly to a handler. Links open source on GitHub with accurate line numbers.

- [`/api/auth/challenge`](#api-auth-challenge)
- [`/api/auth/password_check`](#api-auth-password_check)
- [`/api/game/reboot`](#api-game-reboot)
- [`/api/game/name`](#api-game-name)
- [`/api/game/active_config`](#api-game-active_config)
- [`/api/game/configs_list`](#api-game-configs_list)
- [`/api/game/status`](#api-game-status)
- [`/api/leaders`](#api-leaders)
- [`/api/score/delete`](#api-score-delete)
- [`/api/tournament`](#api-tournament)
- [`/api/leaders/reset`](#api-leaders-reset)
- [`/api/tournament/reset`](#api-tournament-reset)
- [`/api/scores/claimable`](#api-scores-claimable)
- [`/api/scores/claim`](#api-scores-claim)
- [`/api/players`](#api-players)
- [`/api/player/update`](#api-player-update)
- [`/api/player/scores`](#api-player-scores)
- [`/api/mode/champs`](#api-mode-champs)
- [`/api/personal/bests`](#api-personal-bests)
- [`/api/player/scores/reset`](#api-player-scores-reset)
- [`/api/adjustments/status`](#api-adjustments-status)
- [`/api/adjustments/name`](#api-adjustments-name)
- [`/api/adjustments/capture`](#api-adjustments-capture)
- [`/api/adjustments/restore`](#api-adjustments-restore)
- [`/api/settings/get_claim_methods`](#api-settings-get_claim_methods)
- [`/api/settings/set_claim_methods`](#api-settings-set_claim_methods)
- [`/api/settings/get_tournament_mode`](#api-settings-get_tournament_mode)
- [`/api/settings/set_tournament_mode`](#api-settings-set_tournament_mode)
- [`/api/settings/get_show_ip`](#api-settings-get_show_ip)
- [`/api/settings/set_show_ip`](#api-settings-set_show_ip)
- [`/api/time/midnight_madness_available`](#api-time-midnight_madness_available)
- [`/api/time/get_midnight_madness`](#api-time-get_midnight_madness)
- [`/api/time/set_midnight_madness`](#api-time-set_midnight_madness)
- [`/api/time/trigger_midnight_madness`](#api-time-trigger_midnight_madness)
- [`/api/settings/factory_reset`](#api-settings-factory_reset)
- [`/api/settings/reboot`](#api-settings-reboot)
- [`/api/last_ip`](#api-last_ip)
- [`/api/wifi/status`](#api-wifi-status)
- [`/api/network/peers`](#api-network-peers)
- [`/api/set_date`](#api-set_date)
- [`/api/get_date`](#api-get_date)
- [`/api/version`](#api-version)
- [`/api/fault`](#api-fault)
- [`/api/export/scores`](#api-export-scores)
- [`/api/import/scores`](#api-import-scores)
- [`/api/memory-snapshot`](#api-memory-snapshot)
- [`/api/logs`](#api-logs)
- [`/api/formats/available`](#api-formats-available)
- [`/api/formats/set`](#api-formats-set)
- [`/api/formats/active`](#api-formats-active)
- [`/api/diagnostics/switches`](#api-diagnostics-switches)
- [`/api/update/check`](#api-update-check)
- [`/api/update/apply`](#api-update-apply)
- [`/api/in_ap_mode`](#api-in_ap_mode)
- [`/api/in_ap_mode`](#api-in_ap_mode)
- [`/api/settings/set_vector_config`](#api-settings-set_vector_config)
- [`/api/available_ssids`](#api-available_ssids)

---

<a id="api-auth-challenge"></a>
## `/api/auth/challenge`

- **Handler:** [`get_challenge`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L330)


Request a new authentication challenge

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Challenge issued
- `429` - Too many active challenges

**Response body:** JSON containing a single challenge token.

```
{
    "challenge": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

<a id="api-auth-password_check"></a>
## `/api/auth/password_check`

- **Handler:** [`check_password`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L372)
- Authentication: Required (see [Authentication guide](authentication.md)).

Convenience method to verify credentials without side effects

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Credentials accepted
- `401` - Credentials rejected

**Response body:** Acknowledgement string

```
"ok"
```

<a id="api-game-reboot"></a>
## `/api/game/reboot`

- **Handler:** [`app_reboot_game`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L408)
- Authentication: Required (see [Authentication guide](authentication.md)).

Power-cycle the pinball machine and restart the scheduled tasks

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Reboot triggered

**Response body:** Empty body; returns OK on success

```
"ok"
```

<a id="api-game-name"></a>
## `/api/game/name`

- **Handler:** [`app_game_name`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L432)


Get the human-friendly title of the active game configuration

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Active game returned

**Response body:** Plain-text game name

```
"Attack from Mars"
```

<a id="api-game-active_config"></a>
## `/api/game/active_config`

- **Handler:** [`app_game_config_filename`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L451)


Get the filename of the active game configuration. Note that on EM systems this is the same as the game name.

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Active configuration returned

**Response body:** JSON object identifying the configuration file in use

```
{
    "active_config": "AttackMars_11"
}
```

<a id="api-game-configs_list"></a>
## `/api/game/configs_list`

- **Handler:** [`app_game_configs_list`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L477)


List all available game configuration files

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Configurations listed

**Response body:** Mapping of configuration filenames to human-readable titles

```
{"F14_L1": {"name": "F14 Tomcat", "rom": "L1"}, "Taxi_L4": {"name": "Taxi", "rom": "L4"}}
        {
            "F14_L1": {
                "name": "F14 Tomcat",
                "rom": "L1"
            },
            "Taxi_L4": {
                "name": "Taxi",
                "rom": "L4"
            }
        }
```

<a id="api-game-status"></a>
## `/api/game/status`

- **Handler:** [`app_game_status`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L506)


Retrieve the current game status such as ball in play, scores, and anything else the configured game supports

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Status returned

**Response body:** JSON object describing current play state, score, and timers

```
{
    "GameActive": true,
    "BallInPlay": 2,
    "Scores": [1000, 0, 0, 0]
}
```

<a id="api-leaders"></a>
## `/api/leaders`

- **Handler:** [`app_leaderBoardRead`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L559)


Fetch the main leaderboard

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Leaderboard returned

**Response body:** Sorted list of leaderboard entries with rank and relative times

```
[
    {
        "initials": "ABC",
        "score": 123456,
        "rank": 1,
        "ago": "2h"
    }
]
```

<a id="api-score-delete"></a>
## `/api/score/delete`

- **Handler:** [`app_scoreDelete`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L584)
- Authentication: Required (see [Authentication guide](authentication.md)).

Delete one or more score entries from a leaderboard

### Request

#### Body parameters

- `delete` list required - Collection of score objects containing ``score`` and ``initials``.
- `list` string required - Target list name (e.g. leaders or tournament)

### Response

#### Status codes

- `200` - Scores removed

**Response body:** Confirmation indicator

```
{"success": true}
```

<a id="api-tournament"></a>
## `/api/tournament`

- **Handler:** [`app_tournamentRead`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L632)


Read the tournament leaderboard

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Tournament leaderboard returned

**Response body:** List of tournament scores sorted by game order

```
[
    {
        "initials": "ABC",
        "score": 123456,
        "game": 1
    }
]
```

<a id="api-leaders-reset"></a>
## `/api/leaders/reset`

- **Handler:** [`app_resetScores`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L656)
- Authentication: Required (see [Authentication guide](authentication.md)).

Clear the main leaderboard

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Scores cleared


```
"ok"
```

<a id="api-tournament-reset"></a>
## `/api/tournament/reset`

- **Handler:** [`app_tournamentClear`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L675)
- Authentication: Required (see [Authentication guide](authentication.md)).

Clear tournament standings and resets the game counter

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Tournament data cleared


```
"ok"
```

<a id="api-scores-claimable"></a>
## `/api/scores/claimable`

- **Handler:** [`app_getClaimableScores`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L696)


List recent claimable plays

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Claimable scores returned

**Response body:** Collection of unclaimed score records

```
[
    {
        "score": 12345,
        "player_index": 0,
        "game": 1
    }
]
```

<a id="api-scores-claim"></a>
## `/api/scores/claim`

- **Handler:** [`app_claimScore`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L722)


Apply initials to an unclaimed score

### Request

#### Body parameters

- `initials` string required - Player initials to record
- `player_index` int required - Player slot or position associated with the score
- `score` int required - Score value to claim

### Response

#### Status codes

- `200` - Score claimed


```
"ok"
```

<a id="api-players"></a>
## `/api/players`

- **Handler:** [`app_getPlayers`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L758)


List registered players

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Player list returned

**Response body:** Mapping of player IDs to initials and names

```
{
    "0": {
        "initials": "ABC",
        "name": "Alice"
    }
}
```

<a id="api-player-update"></a>
## `/api/player/update`

- **Handler:** [`app_updatePlayer`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L790)
- Authentication: Required (see [Authentication guide](authentication.md)).

Update a stored player record

### Request

#### Body parameters

- `id` int required - Player ID to update
- `initials` string required - Up to three alphabetic characters
- `full_name` string optional - Player display name (truncated to 16 characters)

### Response

#### Status codes

- `200` - Record updated


```
"ok"
```

<a id="api-player-scores"></a>
## `/api/player/scores`

- **Handler:** [`app_getScores`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L845)


Fetch all scores for a specific player

### Request

#### Body parameters

- `id` int required - Player index to inspect

### Response

#### Status codes

- `200` - Player scores returned

**Response body:** Sorted list of score entries with rank, initials, and timestamps

```
[
    {
        "score": 10000,
        "rank": 1,
        "initials": "ABC",
        "date": "2024-01-01",
        "ago": "1d"
    }
]
```

<a id="api-mode-champs"></a>
## `/api/mode/champs`

- **Handler:** [`app_getModeChamps`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L905)


Fetch mode champions data from the game

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Mode champions data returned

**Response body:** Dictionary of mode champions with initials and scores

```
{
    "Biggest Liar": {
        "initials": "ABC",
        "scores": [25, 8]
    },
    "Top Boat Rocker": {
        "initials": "XYZ",
        "scores": [42]
    }
}
```

<a id="api-personal-bests"></a>
## `/api/personal/bests`

- **Handler:** [`app_personal_bests`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L935)


Return the best score for each registered player

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Personal bests returned

**Response body:** Leaderboard of each player's highest score

```
[
    {
        "player_id": 0,
        "initials": "ABC",
        "score": 12345,
        "rank": 1
    }
]
```

<a id="api-player-scores-reset"></a>
## `/api/player/scores/reset`

- **Handler:** [`app_resetIndScores`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L995)
- Authentication: Required (see [Authentication guide](authentication.md)).

Clear all scores for a single player

### Request

#### Query parameters

- `id` int required - Player index whose scores should be erased

### Response

#### Status codes

- `200` - Scores cleared


```
"ok"
```

<a id="api-adjustments-status"></a>
## `/api/adjustments/status`

- **Handler:** [`app_getAdjustmentStatus`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1024)


Get the status of each adjustment bank

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Adjustment metadata returned

**Response body:** List of adjustment profiles with [Name, Active, Exists], along with a flag indicating overall support

```
{
    "profiles": [
        ["Free Play", false, true],
        ["Arcade", true, true],
        ["", false, false],
        ["", false, false]
    ],
    "adjustments_support": true
}
```

<a id="api-adjustments-name"></a>
## `/api/adjustments/name`

- **Handler:** [`app_setAdjustmentName`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1052)
- Authentication: Required (see [Authentication guide](authentication.md)).

Set the name of an adjustment profile

### Request

#### Body parameters

- `index` int required - Adjustment slot to rename
- `name` string required - New name for the slot

### Response

#### Status codes

- `200` - Name updated


```
"ok"
```

<a id="api-adjustments-capture"></a>
## `/api/adjustments/capture`

- **Handler:** [`app_captureAdjustments`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1084)
- Authentication: Required (see [Authentication guide](authentication.md)).

Capture current adjustments into a profile

### Request

#### Body parameters

- `index` int required - Destination profile for captured adjustments

### Response

#### Status codes

- `200` - Adjustments stored


```
"ok"
```

<a id="api-adjustments-restore"></a>
## `/api/adjustments/restore`

- **Handler:** [`app_restoreAdjustments`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1109)
- Authentication: Required (see [Authentication guide](authentication.md)).
- Cooldown: 5s

Restore adjustments from a saved profile

### Request

#### Body parameters

- `index` int required - Adjustment profile to restore

### Response

#### Status codes

- `200` - Adjustments restored


```
"ok"
```

<a id="api-settings-get_claim_methods"></a>
## `/api/settings/get_claim_methods`

- **Handler:** [`app_getScoreCap`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1137)


Read score entry methods

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Claim methods returned

**Response body:** All keys are available methods for entering initials, only enabled methods are true

```
{
    "on-machine": true,
    "web-ui": false
}
```

<a id="api-settings-set_claim_methods"></a>
## `/api/settings/set_claim_methods`

- **Handler:** [`app_setScoreCap`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1162)
- Authentication: Required (see [Authentication guide](authentication.md)).

Configure which score claim methods are enabled

### Request

#### Body parameters

- `on-machine` bool optional - Allow initials entry on the physical game
- `web-ui` bool optional - Allow initials entry via the web interface

### Response

#### Status codes

- `200` - Preferences updated


```
"ok"
```

<a id="api-settings-get_tournament_mode"></a>
## `/api/settings/get_tournament_mode`

- **Handler:** [`app_getTournamentMode`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1195)


Get whether tournament mode is enabled

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Tournament mode returned

**Response body:** Flag indicating tournament mode state

```
{"tournament_mode": true}
```

<a id="api-settings-set_tournament_mode"></a>
## `/api/settings/set_tournament_mode`

- **Handler:** [`app_setTournamentMode`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1213)
- Authentication: Required (see [Authentication guide](authentication.md)).

Enable or disable tournament mode

### Request

#### Body parameters

- `tournament_mode` bool required - New tournament mode setting

### Response

#### Status codes

- `200` - Setting saved


```
"ok"
```

<a id="api-settings-get_show_ip"></a>
## `/api/settings/get_show_ip`

- **Handler:** [`app_getShowIP`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1240)


Check whether the IP address is shown on the display

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Preference returned

**Response body:** Flag indicating whether the IP is displayed

```
{"show_ip": true}
```

<a id="api-settings-set_show_ip"></a>
## `/api/settings/set_show_ip`

- **Handler:** [`app_setShowIP`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1257)
- Authentication: Required (see [Authentication guide](authentication.md)).

Set whether the IP address should be shown on the display

### Request

#### Body parameters

- `show_ip` bool required - Whether to show the IP address on screen

### Response

#### Status codes

- `200` - Preference updated


```
"ok"
```

<a id="api-time-midnight_madness_available"></a>
## `/api/time/midnight_madness_available`

- **Handler:** [`app_midnightMadnessAvailable`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1286)


Report if Midnight Madness mode is supported

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Availability returned

**Response body:** Flag indicating if the game supports Midnight Madness

```
{"available": true}
```

<a id="api-time-get_midnight_madness"></a>
## `/api/time/get_midnight_madness`

- **Handler:** [`app_getMidnightMadness`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1306)


Read Midnight Madness configuration

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Configuration returned

**Response body:** Flags describing whether Midnight Madness is enabled and always on

```
{
    "enabled": true,
    "always": false
}
```

<a id="api-time-set_midnight_madness"></a>
## `/api/time/set_midnight_madness`

- **Handler:** [`app_setMidnightMadness`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1331)
- Authentication: Required (see [Authentication guide](authentication.md)).

Set Midnight Madness configuration

### Request

#### Body parameters

- `always` bool required - Keep Midnight Madness enabled for all games
- `enabled` bool required - Enable timed Midnight Madness events

### Response

#### Status codes

- `200` - Configuration saved


```
"ok"
```

<a id="api-time-trigger_midnight_madness"></a>
## `/api/time/trigger_midnight_madness`

- **Handler:** [`app_triggerMidnightMadness`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1362)


Immediately trigger Midnight Madness

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Event triggered


```
"ok"
```

<a id="api-settings-factory_reset"></a>
## `/api/settings/factory_reset`

- **Handler:** [`app_factoryReset`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1380)
- Authentication: Required (see [Authentication guide](authentication.md)).

Perform a full factory reset of Vector and the pinball machine

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Reset initiated


```
"ok"
```

<a id="api-settings-reboot"></a>
## `/api/settings/reboot`

- **Handler:** [`app_reboot`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1419)
- Authentication: Required (see [Authentication guide](authentication.md)).

Reboot the Pinball machine

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Reboot initiated


```
"ok"
```

<a id="api-last_ip"></a>
## `/api/last_ip`

- **Handler:** [`app_getLastIP`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1444)


Get the last known IP address

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - IP returned

**Response body:** Last recorded IP address

```
{"ip": "192.168.0.10"}
```

<a id="api-wifi-status"></a>
## `/api/wifi/status`

- **Handler:** [`app_getWifiStatus`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1462)


Get the configured Wi-Fi SSID and signal strength

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Status returned

**Response body:** Current Wi-Fi connection status

```
{
    "ssid": "MyNetwork",
    "rssi": -40,
    "connected": true
}
```

<a id="api-network-peers"></a>
## `/api/network/peers`

- **Handler:** [`app_getPeers`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1498)


List other vector devices discovered on the local network

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Peer map returned

**Response body:** Mapping of peer identifiers to network information

```
{
    "192.168.4.243": {
        "name": "Pinbot",
        "self": true
    }
}
```

<a id="api-set_date"></a>
## `/api/set_date`

- **Handler:** [`app_setDateTime`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1526)
- Authentication: Required (see [Authentication guide](authentication.md)).

Set Vector's date and time

### Request

#### Body parameters

- `date` list required - RTC tuple [year, month, day, hour, minute, second]

### Response

#### Status codes

- `200` - Clock updated


```
"ok"
```

<a id="api-get_date"></a>
## `/api/get_date`

- **Handler:** [`app_getDateTime`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1552)


Read the current time according to Vector

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - RTC timestamp returned

**Response body:** Tuple containing RTC date/time fields

```
{"date": [2024, 1, 1, 0, 12, 0, 0]}
```

<a id="api-version"></a>
## `/api/version`

- **Handler:** [`app_version`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1572)


Get the software version. Note: this is the version for the target hardware (what the user sees) and not the release version.

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Version returned

**Response body:** Current firmware version string

```
{"version": "1.0.0"}
```

<a id="api-fault"></a>
## `/api/fault`

- **Handler:** [`app_install_fault`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1591)


Get the list of currently active faults

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Faults returned

**Response body:** Collection of fault flags and details

```
{"faults": []}
```

<a id="api-export-scores"></a>
## `/api/export/scores`

- **Handler:** [`app_export_leaderboard`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1613)


Export all leaderboard data

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Leaderboard export file returned


```
{
        "scores": {"tournament": [{"initials": "AAA", "score": 938479, "index": 2, "game": 0}],
        "leaders": [{"initials": "MSM", "date": "02/04/2025", "full_name": "Maxwell Mullin", "score": 2817420816}]},
        "version": 1
```

<a id="api-import-scores"></a>
## `/api/import/scores`

- **Handler:** [`app_import_leaderboard`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1635)
- Authentication: Required (see [Authentication guide](authentication.md)).

Import leaderboard data from an uploaded file

### Request

#### Body parameters

- `file` bytes required - Score export file content

### Response

#### Status codes

- `200` - Import completed

**Response body:** Success indicator

```
{"success": true}
```

<a id="api-memory-snapshot"></a>
## `/api/memory-snapshot`

- **Handler:** [`app_memory_snapshot`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1662)


Stream a snapshot of memory contents

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Snapshot streaming

**Response body:** Text stream of byte values

<a id="api-logs"></a>
## `/api/logs`

- **Handler:** [`app_getLogs`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1680)
- Authentication: Required (see [Authentication guide](authentication.md)).
- Cooldown: 10s
- Single instance: Yes

Download the system log file

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Log download streaming

**Response body:** Log file content

<a id="api-formats-available"></a>
## `/api/formats/available`

- **Handler:** [`app_list_available_formats`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1706)


Get the list of available game formats

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Formats returned

**Response body:** Collection of available game formats with metadata and configuration options

```
[
    {
        "id": 0,
        "name": "Standard",
        "description": "Manufacturer standard game play"
    }
]
```

<a id="api-formats-set"></a>
## `/api/formats/set`

- **Handler:** [`app_set_current_format`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1733)
- Authentication: Required (see [Authentication guide](authentication.md)).

Set the active game format

### Request

#### Body parameters

- `format_id` int required - Format identifier to activate
- `options` dict optional - Configuration options for the selected format

### Response

#### Status codes

- `200` - Format set successfully

<a id="api-formats-active"></a>
## `/api/formats/active`

- **Handler:** [`app_get_active_formats`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1782)


Get the currently active game format

### Request

No parameters inferred.

### Response

No structured response documented.

<a id="api-diagnostics-switches"></a>
## `/api/diagnostics/switches`

- **Handler:** [`app_get_switch_diagnostics`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1816)


Get diagnostic information for all switches

### Request

No parameters inferred.

### Response

No structured response documented.

<a id="api-update-check"></a>
## `/api/update/check`

- **Handler:** [`app_updates_available`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1843)
- Cooldown: 10s

Get the metadata for the latest available software version. This does not download or apply the update.

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Update metadata returned

**Response body:** JSON payload describing available updates

```
{
    "release_page": "https://github.com/...",
    "notes": "Another Great Release! Here's what we changed",
    "published_at": "2025-12-30T17:54:49+00:00",
    "url": "https://github.com/...",
    "version": "1.9.0"
}
```

<a id="api-update-apply"></a>
## `/api/update/apply`

- **Handler:** [`app_apply_update`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1878)
- Authentication: Required (see [Authentication guide](authentication.md)).

Download and apply a software update from the provided URL.

### Request

#### Body parameters

- `url` string required - Signed update package URL
- `skip_signature_check` bool optional - Bypass signature validation (for developer builds)

### Response

#### Status codes

- `200` - Streaming progress updates

**Response body:** Sequence of JSON log entries with ``log`` and ``percent`` fields

```
{
    "log": "Starting update",
    "percent": 0
}
```

<a id="api-in_ap_mode"></a>
## `/api/in_ap_mode`

- **Handler:** [`app_inAPMode`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1931)


Indicates if Vector is running in AP or app mode

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Mode reported

**Response body:** Flag showing AP mode status

```
{"in_ap_mode": false}
```

<a id="api-in_ap_mode"></a>
## `/api/in_ap_mode`

- **Handler:** [`app_inAPMode`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1954)


No description provided.

### Request

No parameters inferred.

### Response

No structured response documented.

<a id="api-settings-set_vector_config"></a>
## `/api/settings/set_vector_config`

- **Handler:** [`app_setWifi`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L1959)


[AP Mode Only] Configure Wi-Fi credentials and default game

### Request

#### Body parameters

- `ssid` string required - Wi-Fi network name
- `wifi_password` string required - Wi-Fi network password
- `vector_password` string required - Password for authenticated API access
- `game_config_filename` string required - Game configuration filename to load

### Response

#### Status codes

- `200` - Configuration saved


```
"ok"
```

<a id="api-available_ssids"></a>
## `/api/available_ssids`

- **Handler:** [`app_getAvailableSSIDs`](https://github.com/warped-pinball/vector/blob/main/src/common/backend.py#L2010)


[AP Mode Only] Scan for nearby Wi-Fi networks

### Request

No parameters inferred.

### Response

#### Status codes

- `200` - Networks listed

**Response body:** Array of SSID records with signal quality and configuration flag

```
[
    {
        "ssid": "MyNetwork",
        "rssi": -40,
        "configured": true
    }
]
```
