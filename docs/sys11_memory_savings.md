# System 11 Memory-Saving Hotspots

The System 11 firmware bundles everything under `src/common` plus the System 11
specific sources. To identify the most impactful trim points, the largest
artifacts (by compressed and uncompressed size) were enumerated and reviewed for
low-risk optimizations. The measurements below were taken directly from the
current tree.

## 1. Trim the Pico.css bundle
- **What**: `src/common/web/css/pico.min.css`
- **Size**: 83,320 bytes on disk, 11,642 bytes after gzip.【364e28†L8-L8】【9ae551†L8-L9】
- **Why it matters**: The stylesheet is the single largest asset in the web UI
  bundle for System 11 builds. Because it ships in full even when only a small
  subset of the Pico.css components are used, it dominates the flash footprint.
- **Suggested change**: Replace the generic Pico.css build with a curated
  stylesheet that only keeps the selectors used by `admin.html`, `players.html`,
  and `scores.html`. A simple PostCSS purge step or a hand-maintained SCSS file
  would cut tens of kilobytes while keeping the layout intact.

## 2. Simplify the logo asset
- **What**: `src/common/web/svg/logo.svg`
- **Size**: 54,183 bytes on disk, 21,273 bytes after gzip.【364e28†L9-L9】【983d24†L8-L8】
- **Why it matters**: This single SVG consumes more than any HTML page in the
  build. The intricate vector paths (visible when opening the file) encode far
  more detail than is required for on-device display.
- **Suggested change**: Replace the SVG with a simplified, flattened export (or
  even a small PNG/WebP). Running the existing `scour` step with aggressive
  path-simplification or re-exporting from the source artwork at a lower point
  count can save 15–20 KB without touching code.

## 3. Swap the RSA verifier for a lighter primitive
- **What**: `src/common/rsa/*.py` loaded solely to support `rsa.pkcs1.verify`
  inside the OTA updater.【b66eb4†L170-L185】
- **Size**: 31,377 bytes of Python modules included in every System 11 image.【364e28†L10-L10】
- **Why it matters**: The updater only needs signature verification, yet the
  bundled RSA library pulls in key generation, PKCS#1 padding helpers, and
  compatibility shims. This is one of the largest pure-Python bundles in the
  firmware.
- **Suggested change**: Replace the RSA dependency with a compact verifier—for
  example, reuse the existing Curve25519 arithmetic in `src/common/curve25519.py`
  to host an Ed25519 or X25519-based signature check, or ship a pre-computed
  DER-decoded modulus and a tiny modular-exponentiation helper. Dropping
  `src/common/rsa` saves ~30 KB immediately for System 11 and every other build.

## 4. Replace the custom HTTP client with `urequests`
- **What**: `src/common/mrequests/` used only by `download_update` for OTA【b66eb4†L188-L220】
- **Size**: 24,198 bytes across `mrequests.py` and its helpers.【364e28†L11-L11】
- **Why it matters**: The local fork replicates a full desktop-like API,
  including redirect handling, chunked transfer decoding, and querystring tools.
  That feature set is unused by the updater, yet all of the code has to be
  frozen into flash.
- **Suggested change**: Switch the updater to `urequests` (or a purpose-built
  1–2 KB shim that just downloads a stream). Combined with the TODO already in
  `download_update` to use buffered reads, this drops another ~24 KB from the
  System 11 image while also reducing RAM churn during downloads.

## 5. Factor common System 11 game metadata
- **What**: `src/sys11/config/*.json`
- **Size**: 41,051 bytes of JSON (14,004 bytes compressed) duplicated across 34
  game files.【1d9c85†L13-L13】
- **Why it matters**: Every game definition repeats large blocks—`Memory`,
  `Adjustments`, `HSRewards`, `Switches`, etc.—even when they match the generic
  template.【2de04f†L12-L68】【b99cd2†L12-L73】 Those repetitions consume flash in
  every build.
- **Suggested change**: Promote the shared sections from
  `GenericSystem11_.json` into a base template and only store per-game deltas
  (address overrides, feature flags). A tiny merge step in `dev/build.py` can
  assemble the full config at build time, cutting tens of kilobytes while
  keeping the JSON reader unchanged.
