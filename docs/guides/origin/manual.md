<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">Origin Installation & Operation Manual</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>



What Origin is, how to install and configure it, how to bring your Vector
machines online with it, and how to run it day to day.

If you just want it running, start with the
[Origin Quick Start](quick-start.md) and come back here for detail.

## Table of contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Connecting your machines](#connecting-your-machines)
- [Remote access](#remote-access)
- [Operating Origin](#operating-origin)
- [Backup and restore](#backup-and-restore)
- [Updating](#updating)
- [Troubleshooting](#troubleshooting)

## How it works

Origin runs as a small set of Docker containers on a computer you own:

| Service | Role |
| --- | --- |
| **app** | The FastAPI web application and API. Serves the UI on port `8000` and listens for signed game-event datagrams on UDP `6809`. |
| **postgres** | PostgreSQL database holding machines, games, scores, and accounts. Not exposed to the host network. |
| **flyway** | Runs database migrations once on startup, then exits. |
| **ray** | A bridge that runs with host networking so it can see the LAN, discover Vector boards, and make the authenticated calls that register Origin as each board's event listener. |
| **cloudflared** | Optional. A Cloudflare Tunnel for remote access without opening router ports. Off unless you enable it. |
| **pgadmin** | Optional database admin UI. Publishes no ports by default. |

Each Vector board sends its live game state and end-of-game results as UDP
datagrams to **one** registered listener, and signs every datagram with a shared
secret. With no listener registered a board sends nothing. Ray performs that
registration for you, so from the owner's point of view a machine just needs to
be discovered.

## Requirements

- A host that stays powered on and on the **same LAN / broadcast domain** as your
  pinball machines. Ray's discovery does not cross subnets or VLANs.
- **Docker Engine** and the **Docker Compose** plugin.
- Architecture: `linux/amd64` or `linux/arm64` (Raspberry Pi 4/5 class or better;
  a Pi 3 will run it but slowly, especially photo score reading).
- Roughly 2 GB free RAM and a few GB of disk for the database volume and uploads.
- Outbound internet on first run (to pull images) and whenever you update. Normal
  operation needs no internet unless you use remote access or email features.

## Installation

### With Docker Compose (recommended)

```bash
git clone https://github.com/warped-pinball/origin.git
cd origin
docker compose up -d
```

This starts every core service, runs database migrations, and leaves the stack
running in the background. Watch it come up with:

```bash
docker compose ps
docker compose logs -f app
```

The UI is served at `http://<host>:8000`. The first account you create at
**Sign up** becomes the admin.

<!-- TODO(owner): the committed docker-compose.yml builds images from source and
     binds the app to 127.0.0.1 by default. Decide and document the supported
     customer path:
       (a) clone + `docker compose up -d` as above, with APP_BIND=0.0.0.0 set in
           .env for LAN access; or
       (b) a slimmed compose file that pulls prebuilt images
           ghcr.io/warped-pinball/origin, -ray, and -flyway (built for amd64 and
           arm64 by .github/workflows/docker-publish.yml; `latest` is published
           on GitHub Releases).
     Update this section and step 3 of the quick start to match. -->

### Prebuilt images

Release images are published to the GitHub Container Registry:

- `ghcr.io/warped-pinball/origin` — the app
- `ghcr.io/warped-pinball/origin-ray` — the LAN bridge
- `ghcr.io/warped-pinball/origin-flyway` — the database migrator

<!-- TODO(owner): publish a compose file that references these tags, or a
     `docker run` recipe for the app + an external Postgres, and link it here. -->

## Configuration

Copy `.env.example` to `.env` in the repository root and set only what you need —
every value is optional and has a working default.

| Variable | Description | Default |
| --- | --- | --- |
| `APP_BIND` | Host interface the web UI binds to. `127.0.0.1` is loopback only; set `0.0.0.0` to reach it from other devices on the LAN. | `127.0.0.1` |
| `APP_PORT` | Host port for the web UI. | `8000` |
| `DATABASE_URL` | Database connection string. Leave as-is for the bundled PostgreSQL. | `postgresql+asyncpg://postgres@postgres:5432/origin` |
| `UVICORN_WORKERS` | Worker processes for the app. Raise to match CPU cores on a busy or low-power host. | `1` |
| `SEAT_CLAIM_TTL_MINUTES` | How long a scanned "I'll be player N" seat claim stays pending before it expires. | `240` |
| `SCORE_VALIDATOR` | Photo-score reviewer hints: `local-ocr` re-reads the photo on the host; `manual` turns hints off. | `local-ocr` |
| `SECURE_COOKIES` | Set `true` when serving over HTTPS (for example behind the tunnel) so session cookies get the `Secure` flag. | `false` |
| `COMPOSE_PROFILES` | Set to `tunnel` to start the `cloudflared` service. | _unset_ |
| `CLOUDFLARED_TUNNEL_TOKEN` | Tunnel token from the Cloudflare Zero Trust dashboard. | _unset_ |

After editing `.env`, apply it with `docker compose up -d`.

<!-- TODO(owner): confirm this list against .env.example / docker-compose.yml at
     release and drop any variable that is dev-only (RAY_PASSWORD, MACHINE_MODE,
     SIMULATED_CONNECTOR_FIXTURE, PGADMIN_* are not owner-facing). -->

### Database

The bundled PostgreSQL uses trust authentication and is reachable only from the
other containers — it is **not** published to the host network, so there is no
database password to manage. Its data lives in the `postgres_data` Docker volume
(see [Backup and restore](#backup-and-restore)).

For a tiny test setup you can run the app against SQLite instead by setting
`DATABASE_URL=sqlite+aiosqlite:///./data/app.db`, but PostgreSQL is the supported
configuration for anything real.

## Connecting your machines

1. Make sure each Vector board is installed, joined to your WiFi, and opens in a
   browser (its owner's guide covers this).
2. Keep the Origin host on the **same network**. Ray discovers boards by
   listening for their announcements on the LAN; it cannot reach a board on a
   different subnet or an isolated "IoT" WiFi.
3. Discovered machines show up on the **Games** page. Open one to see live
   status.

<!-- TODO(owner): document the board Admin/Service password flow. If a board has
     a password set on its own Service page, Ray needs it to complete
     registration and to change adjustments/formats. Describe exactly where the
     owner enters that password in the Origin UI, and what "connected" vs
     "discovered but not connected" looks like on the Games page. -->

Once a machine is connected, play a game: the score updates live in the UI and on
the big screen, and the finished game is recorded to the leaderboard. Enter
player names on the machine (or claim the play in Origin) so scores are
attributed to people rather than typed initials.

## Remote access

The stack ships an opt-in **Cloudflare Tunnel** so you can reach Origin from
outside your home or arcade without opening any ports on your router.

1. In the Cloudflare Zero Trust dashboard, create a tunnel and copy its token.
2. In `.env`:

   ```bash
   COMPOSE_PROFILES=tunnel
   CLOUDFLARED_TUNNEL_TOKEN=<your token>
   SECURE_COOKIES=true
   ```

3. Point the tunnel's public hostname at `http://app:8000` in its ingress rules.
4. `docker compose up -d`.

Your Origin instance is now reachable at the hostname you configured, over HTTPS,
with nothing exposed on your router.

<!-- TODO(owner): note the recommended hostname pattern (e.g.
     your-arcade.example.com) and whether QR-code links depend on that hostname
     being stable, since /qr/{token} URLs are printed onto physical placards. -->

## Operating Origin

### Big screen

Open **Big Screen Setup** (`/big-screen/setup`) to configure the number of
side-by-side panels, which games appear, tournament filtering, and whether live
games are shown. From there you can open the big screen in a browser tab or
**Cast** it to any Chromecast on the network; the Cast button turns blue while
casting. Some ad blockers and privacy extensions block the Google Cast
framework — allow it on the setup page if casting does not start.

### Tournaments

<!-- TODO(owner): short walkthrough — create a tournament, add games to it,
     how ordered scores are captured, how the big-screen tournament filter ties
     in. -->

### Scan-to-claim QR codes

Each machine can carry QR codes that link to `/qr/{token}`. A player who scans one
lands on that machine's claim board and can:

- claim a seat ("I'll be player 2") before or during a game so the finished game
  is credited to their account; or
- claim an unclaimed play from the machine's most recent finished game (plays
  already owned by an account are locked).

An admin registers a new QR code by scanning it: an unrecognised token shows a
machine picker. `/scan` offers an in-browser scanner plus a manual picker.

<!-- TODO(owner): how owners generate/print the QR placards, and any per-machine
     limit. -->

### Scores from non-Vector machines

`/submit-score` captures a back box that has no Vector board. Because score
displays flicker on camera, the UI asks for a ~2-second video by default and
merges the frames into one clean image before reading it; a still photo also
works. An admin first runs the machine's **score setup wizard**
(`/machines/{id}/score-setup`) once — take a reference photo with all final
scores showing, choose the display type and player/digit counts, and drag a box
around each player's score. After that, player submissions are aligned to the
reference, read with an on-host OCR/CV pipeline, and queued for an admin to
review. Nothing is sent to an external service.

### Accounts and roles

The first account is admin. Admins promote other accounts and see the
permission-gated admin tools on the settings and machine pages. Login is
rate-limited (5 attempts / 5 min) and signup is rate-limited (3 / hour).

<!-- TODO(owner): if email-based login / marketing is a paid add-on rather than
     part of the self-hosted build, say so here and link the product page. -->

## Backup and restore

All persistent data is in Docker volumes:

- `postgres_data` — the database (machines, games, scores, accounts)
- `custom_content_uploads` — uploaded images and score-capture references
- `pgadmin_data` — pgAdmin settings (only if you use pgAdmin)

**Back up the database:**

```bash
docker compose exec -T postgres pg_dump -U postgres origin > origin-$(date +%F).sql
```

**Back up uploads:**

```bash
docker run --rm -v origin_custom_content_uploads:/data -v "$PWD":/backup alpine \
  tar czf /backup/origin-uploads-$(date +%F).tar.gz -C /data .
```

<!-- TODO(owner): confirm the volume names against `docker volume ls` for the
     shipped project name, and give the matching restore commands. -->

**Restore the database** into a fresh stack:

```bash
docker compose up -d postgres
cat origin-YYYY-MM-DD.sql | docker compose exec -T postgres psql -U postgres origin
docker compose up -d
```

Take a backup before every update.

## Updating

```bash
cd origin
git pull
docker compose pull        # if you use prebuilt images
docker compose up -d --build
```

Flyway applies any new database migrations automatically on startup. Watch
`docker compose logs -f flyway app` and confirm the app returns to `healthy`.

<!-- TODO(owner): state the version/upgrade policy — is downgrading supported,
     are migrations reversible, how far back can you jump in one step. -->

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Web UI not reachable from other devices | `APP_BIND` is `0.0.0.0`, not `127.0.0.1`; host firewall allows the port; you are using the host's LAN IP. |
| A machine never appears | The Origin host and the board are on the same subnet/VLAN and WiFi; the board opens in a browser; `docker compose logs -f ray` shows discovery traffic. |
| Machine appears but shows no live scores | The board is connected (not just discovered); play a full game; `docker compose logs -f app` shows incoming `game_state` / `end_of_game` messages on UDP 6809. |
| Scores show but not attributed to a player | Enter names on the machine, or claim the play in Origin / via a QR seat claim. |
| Casting to Chromecast does nothing | Disable ad/privacy blockers for the setup page; confirm the Chromecast is on the same network. |
| Database or migration errors on startup | `docker compose logs flyway`; restore from your latest backup if a migration failed midway. |

For anything else, open an issue at
<https://github.com/warped-pinball/origin/issues> or contact Warped Pinball
support.
