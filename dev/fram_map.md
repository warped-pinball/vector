# FRAM & Serial Flash Memory Map

Hardware: 32 KB FRAM (`0x0000`–`0x7FFF`) + 32 MB Serial Flash  
All values little-endian. FRAM fills from the **top down** for the SPI Data Store; fixed regions occupy the **bottom**.

---

## FRAM — Fixed Regions (Bottom of Address Space)

These regions are the same physical chip but managed outside the SPI Data Store.

### System 11

| Region | Start | End | Size | Notes |
|--------|-------|-----|------|-------|
| Shadow RAM | `0x0000` | `0x07FF` | 2 KB used | Reserved to `0x1FFF` (8 KB) for future growth |
| UpdateStore status | `0x2000` | `0x20FF` | 256 B | Serial flash update tracking |
| Game adjustments | `0x2100` | `0x2340` | 576 B | 4 profiles × (128 B data + 16 B name) |
| Last profile byte | `0x2344` | `0x2344` | 1 B | Index 0–3 of last loaded adjustment profile |
| Logger | `0x2400` | `0x43FF` | 8 KB | Circular log buffer |
| *(reserved)* | `0x4400` | `0x5482` | ~4.2 KB | Expansion space |

### WPC

| Region | Start | End | Size | Notes |
|--------|-------|-----|------|-------|
| Shadow RAM | `0x0000` | `0x1FFF` | 8 KB | Full 8 KB required for WPC |
| Game adjustments | `0x2000` | `0x25FF` | 1.5 KB | 4 profiles × (305 B data + 16 B name); expanded from Sys11 |
| Last profile byte | `0x2344` | `0x2344` | 1 B | Index 0–3 of last loaded adjustment profile |
| Logger | `0x2600` | `0x45FF` | 8 KB | Shifted up vs. Sys11 to make room for larger adjustments |
| *(reserved)* | `0x4600` | `0x4A1E` | ~1 KB | Expansion space |

> WPC removed the serial flash UpdateStore status region.

### Data East

Same fixed layout as WPC.

---

## FRAM — SPI Data Store (Top of Address Space, fills downward)

`top_mem = 32767 (0x7FFF)` is the reference anchor. Records are allocated downward from there.  
All three systems share the same record names and ordering; differences are in record sizes and which records exist.

### System 11 — Map Version 1.0

| Record | Start | End | Record Size | Count | Total |
|--------|-------|-----|-------------|-------|-------|
| MapVersion | `0x7FEF` (32751) | `0x7FFE` (32766) | 16 B | 1 | 16 B |
| names | `0x7D97` (32151) | `0x7FEE` (32750) | 20 B | 30 players | 600 B |
| leaders | `0x7AEB` (31451) | `0x7D96` (32150) | 35 B | 20 | 700 B |
| tournament | `0x762B` (30251) | `0x7AEA` (31450) | 12 B | 100 | 1,200 B |
| individual | `0x555B` (21851) | `0x762A` (30250) | 14 B | 20 scores × 30 players | 8,400 B |
| configuration | `0x54FB` (21755) | `0x555A` (21850) | 96 B | 1 | 96 B |
| extras | `0x54CB` (21707) | `0x54FA` (21754) | 48 B | 1 | 48 B |
| switches | `0x5483` (21635) | `0x54CA` (21706) | 72 B | 1 | 72 B |

**Bottom of used space: `0x5483` (21635)**

### WPC — Map Version 2.0

Scores expanded from 4-byte `uint32` to 8-byte `uint64` throughout.

| Record | Start | End | Record Size | Count | Total |
|--------|-------|-----|-------------|-------|-------|
| MapVersion | `0x7FEF` (32751) | `0x7FFE` (32766) | 16 B | 1 | 16 B |
| names | `0x7D97` (32151) | `0x7FEE` (32750) | 20 B | 30 players | 600 B |
| leaders | `0x7A9F` (31391) | `0x7D96` (32150) | 38 B | 20 | 760 B |
| tournament | `0x7527` (29991) | `0x7A9E` (31390) | 14 B | 100 | 1,400 B |
| individual | `0x4AF7` (19191) | `0x7526` (29990) | 18 B | 20 scores × 30 players | 10,800 B |
| configuration | `0x4A97` (19095) | `0x4AF6` (19190) | 96 B | 1 | 96 B |
| extras | `0x4A67` (19047) | `0x4A96` (19094) | 48 B | 1 | 48 B |
| switches | `0x4A1F` (18975) | `0x4A66` (19046) | 72 B | 1 | 72 B |

**Bottom of used space: `0x4A1F` (18975)**

### Data East — Map Version 2.0

Identical to WPC except the `switches` record does not exist.

| Record | Start | End | Record Size | Count | Total |
|--------|-------|-----|-------------|-------|-------|
| MapVersion | `0x7FEF` (32751) | `0x7FFE` (32766) | 16 B | 1 | 16 B |
| names | `0x7D97` (32151) | `0x7FEE` (32750) | 20 B | 30 players | 600 B |
| leaders | `0x7A9F` (31391) | `0x7D96` (32150) | 38 B | 20 | 760 B |
| tournament | `0x7527` (29991) | `0x7A9E` (31390) | 14 B | 100 | 1,400 B |
| individual | `0x4AF7` (19191) | `0x7526` (29990) | 18 B | 20 scores × 30 players | 10,800 B |
| configuration | `0x4A97` (19095) | `0x4AF6` (19190) | 96 B | 1 | 96 B |
| extras | `0x4A67` (19047) | `0x4A96` (19094) | 48 B | 1 | 48 B |

**Bottom of used space: `0x4A67` (19047)**

---

## Record Field Layouts

All strings are null-padded to their fixed length. Struct format is little-endian (`<`).

### MapVersion — 16 bytes
| Field | Type | Size | Notes |
|-------|------|------|-------|
| version | `16s` | 16 B | e.g. `"Map Ver: 1.0"` (Sys11) or `"Map Ver: 2.0"` (WPC/DE) |

### names — 20 bytes (all systems)
| Field | Type | Size |
|-------|------|------|
| initials | `3s` | 3 B |
| full_name | `16s` | 16 B |

*(1 byte padding to reach 20)*

### leaders — 35 bytes (Sys11) / 38 bytes (WPC & Data East)

| Field | Type (Sys11) | Type (WPC/DE) | Size (Sys11) | Size (WPC/DE) |
|-------|-------------|--------------|-------------|--------------|
| initials | `3s` | `3s` | 3 B | 3 B |
| full_name | `16s` | `16s` | 16 B | 16 B |
| date | `10s` | `10s` | 10 B | 10 B |
| score | `I` (uint32) | `Q` (uint64) | 4 B | **8 B** |

*(1 byte padding in Sys11 to reach 35; 1 byte padding in WPC/DE to reach 38)*

### tournament — 12 bytes (Sys11) / 14 bytes (WPC & Data East)

| Field | Type (Sys11) | Type (WPC/DE) | Size (Sys11) | Size (WPC/DE) |
|-------|-------------|--------------|-------------|--------------|
| initials | `3s` | `3s` | 3 B | 3 B |
| score | `I` (uint32) | `Q` (uint64) | 4 B | **8 B** |
| game | `B` | `B` | 1 B | 1 B |
| index | `B` | `B` | 1 B | 1 B |

*(1 byte padding in Sys11 to reach 12; 1 byte padding in WPC/DE to reach 14)*

### individual — 14 bytes (Sys11) / 18 bytes (WPC & Data East)

| Field | Type (Sys11) | Type (WPC/DE) | Size (Sys11) | Size (WPC/DE) |
|-------|-------------|--------------|-------------|--------------|
| score | `I` (uint32) | `Q` (uint64) | 4 B | **8 B** |
| date | `10s` | `10s` | 10 B | 10 B |

Addressed as a 2D array: `set` = player number (0–29), `index` = score slot (0–19).

### configuration — 96 bytes (all systems)

| Field | Type | Size |
|-------|------|------|
| ssid | `32s` | 32 B |
| password | `32s` | 32 B |
| gamename | `16s` | 16 B |
| Gpassword | `16s` | 16 B |

### extras — 48 bytes (all systems)

| Field | Type | Size | Notes |
|-------|------|------|-------|
| enable | `I` (uint32) | 4 B | Feature flags (see below) |
| other | `I` (uint32) | 4 B | Reserved |
| lastIP | `20s` | 20 B | Last known IP address string |
| message | `20s` | 20 B | Short status/message string |

**`enable` flag bits:**

| Bit | Sys11 flag | WPC / Data East flag |
|-----|-----------|---------------------|
| `0x01` | enter_initials_on_game | enter_initials_on_game |
| `0x02` | claim_scores | claim_scores |
| `0x04` | show_ip_address | show_ip_address |
| `0x08` | tournament_mode | tournament_mode |
| `0x10` | flag5 | WPCTimeOn |
| `0x20` | flag6 | MM_Always |

### switches — 72 bytes (Sys11 and WPC only; not Data East)

| Field | Type | Size | Notes |
|-------|------|------|-------|
| switches | `72B` | 72 B | Per-switch activity counts (72 switch slots) |

---

## Serial Flash — 32 MB (all systems, shared layout)

Address range: `0x000 0000`–`0x1FF FFFF`  
Erase granularity: 64 KB chunks (erase to `0xFF`).  
First and last 64 KB are protectable in 4 KB chunks; middle sections in 64 KB chunks.

### Software Update Store — three 6 MB slots

| Slot | Start | End | Blocks |
|------|-------|-----|--------|
| 1 | `0x001 0000` | `0x060 FFFF` | 1–96 |
| 2 | `0x061 0000` | `0x0C0 FFFF` | 97–192 |
| 3 | `0x0C1 0000` | `0x120 FFFF` | 193–288 |

---

## Future / Planned (from design notes)

These structures are noted in design documents but not yet implemented:

**Player list record (planned — 22 bytes each)**
- Initials + name: 3 + 16 = 19 bytes
- CRC-16 player ID: 2 bytes

**Score list record (planned — 8 bytes each)**
- Score: uint32 (4 bytes)
- Date: 3 bytes
- Flags: 1 byte — `[tournament, _, _, _]`
