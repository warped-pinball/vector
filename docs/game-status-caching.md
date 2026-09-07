# Game Status Caching

## Summary

`/api/game/status` now returns a cached report produced by the existing 4Hz
`poll_fast` task instead of recomputing the report on every HTTP request.

## Motivation

The web UI polls `/api/game/status` frequently (observed ~10 requests/second).
Each request previously called `game_report()`, which reads shadow RAM, performs
BCD conversions, and allocates a fresh result dict, `Scores` list, and several
bytearray slices ([DataMapper.get_in_play_data](../src/classic/DataMapper.py) and
`get_modes`).

The per-request *compute* is small (sub-millisecond to low single-digit ms) and
is not the source of the ~50–70ms baseline latency — that is dominated by the
HTTP framework and WiFi round-trip. However, the per-request *allocations*, at
~10/second continuously, feed MicroPython's garbage collector and contribute to
the periodic ~200ms latency spikes (GC pauses).

Critically, `poll_fast` already runs every 250ms (4Hz) and already calls
`game_report()` on every tick. The report was therefore being computed 4×/second
regardless, *in addition to* once per HTTP request — redundant work.

## Changes

### `src/common/GameStatus.py`

- Added a module-level cache `_last_report` and a `cached_report()` accessor.
  `cached_report()` returns the last report computed by `poll_fast`, falling
  back to a live `game_report()` only if the poller has not run yet (boot-time
  safety, so an early request never returns `None`).
- `poll_fast()` now stores its computed report in `_last_report` and reuses that
  same object for `push_game_state()`.

### `src/common/backend.py`

- The `/api/game/status` route now returns `cached_report()` instead of
  `game_report()`. The pre-existing `# TODO cache me` was removed.

## Effect

- Shadow RAM reads, BCD conversions, and allocations now happen at a fixed 4Hz
  (driven by `poll_fast`) instead of once per HTTP request.
- The route handler becomes an effectively allocation-free dict lookup + return.
- Fewer allocation cycles reduces GC pressure, which should reduce the frequency
  of the ~200ms latency spikes. (The ~50–70ms baseline is framework/WiFi and is
  unaffected by this change.)
- Worst-case data staleness is 250ms, which is imperceptible for a status
  display.

## Scope

This affects all systems that share `src/common/GameStatus.py` (sys11, classic,
whitestar), since they schedule `poll_fast` via the common path. The `wpc`,
`em`, and `data_east` builds maintain their own `GameStatus.py` copies and were
left unchanged.
