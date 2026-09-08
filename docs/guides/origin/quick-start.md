<div style="display: flex; justify-content: space-between; align-items: center; gap: 1rem;">
  <h1 style="margin: 0;">Origin Quick Start (v1.0)</h1>
  <button onclick="window.print()" style="white-space: nowrap;">
    <span aria-hidden="true">🖨️</span> Print This Guide
  </button>
</div>



Fast-path instructions for standing up an **Origin** hub on your own hardware and
pointing your Vector machines at it. Origin is a self-hosted service that collects
live game state and scores from every Vector board on your network and serves
leaderboards, a real-time big-screen view, and tournament tools from one place.

For the full reference — configuration, remote access, backups, and day-to-day
operation — see the [Installation & operation manual](manual.md).

## What you need

- A machine that stays on and stays on the **same LAN** as your pinball machines
  (a mini PC, NUC, or Raspberry Pi 4/5 is plenty — images are built for both
  `amd64` and `arm64`).
- **Docker** and the **Docker Compose** plugin installed on that machine.
- `git` on that machine.
- Your Vector boards already installed, on WiFi, and reachable in a browser (see
  your system's owner's guide if you are not there yet).

## Steps

1. **Get Origin onto the host.**

   ```bash
   git clone https://github.com/warped-pinball/origin.git
   cd origin
   ```

2. **Start the stack.**

   ```bash
   docker compose up -d
   ```

   Compose brings up the app, its PostgreSQL database, the database migrator,
   and the **Ray** bridge that talks to your machines. First start pulls base
   images and builds, so give it a few minutes. Check progress with
   `docker compose ps` — every service should read `healthy` or `running`.

3. **Open the web UI.**

   Browse to <http://localhost:8000> on the host, or `http://<host-ip>:8000`
   from another device on the LAN.

   <!-- TODO(owner): confirm the app is reachable from other LAN devices with the
        shipped compose file. The default binds APP_BIND=127.0.0.1 (loopback
        only); a LAN deployment needs APP_BIND=0.0.0.0. Document the exact knob
        here once decided — see the manual's Configuration section. -->

4. **Create your account.**

   Click **Sign up** and create the first account. The first account on a fresh
   instance automatically becomes the **admin**; everyone who signs up after that
   is a normal player until an admin promotes them.

5. **Connect your machines.**

   Ray watches the LAN and discovers Vector boards automatically. Newly
   discovered machines appear on the **Games** page within a minute or two.

   <!-- TODO(owner): document the exact customer step for machines that have an
        Admin/Service password set on the board — where in the Origin UI the
        password is entered so Ray can register Origin as the board's listener
        (POST /api/origin/target). Until a listener is registered the board
        sends nothing. -->

6. **Put it on the big screen.**

   Open **Big Screen Setup** (`/big-screen/setup`) to pick which games show, how
   many panels, and tournament filters, then open or **Cast** the big-screen
   leaderboard to a Chromecast on your network.

Play a game. Within a few seconds the score should appear live in the web UI and
on the big screen, and the finished game lands on the leaderboard.

## Next steps

- **Remote access** without opening ports on your router — turn on the bundled
  Cloudflare Tunnel: [manual → Remote access](manual.md#remote-access).
- **Back up your data** — everything lives in a Docker volume:
  [manual → Backup and restore](manual.md#backup-and-restore).
- **Scan-to-claim QR codes**, photo score capture for non-Vector machines, and
  tournaments: [manual → Operating Origin](manual.md#operating-origin).
