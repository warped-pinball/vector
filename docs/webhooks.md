# Webhooks

A webhook lets a service off your local network hear about a few board events: the end of a game, a fault being raised or cleared, and the board starting up. The board POSTs each event over HTTPS to one URL you choose.

Webhooks are **off unless you turn them on**. With no webhook registered the board opens no outbound connections for them.

## Registering a webhook

On the board's **Admin** page, go to **Settings > Webhook**. Enter the URL and secret, then select **Save Webhook**. **Check Status** shows where events go and the result of the last attempt. **Turn Off Webhook** stops sending and forgets the URL and secret.

To set it up from a script instead, call the authenticated [`/api/webhook/target`](routes.md) route (see [Authentication](authentication.md) for signing the request):

```json
{"url": "https://example.com/hooks/vector", "secret": "a-long-random-string"}
```

- `url` must start with `https://` and be at most 160 characters.
- `secret` is 1-64 ASCII characters. The board never sends it; it only signs with it.

The registration is saved in the board's FRAM, so it survives reboots and software updates. To stop sending and forget the registration, send `{"enable": false}`. A factory reset also removes it.

[`/api/webhook/status`](routes.md) (authenticated) shows the registered URL, how many events are waiting, and the result of the last attempt. That's useful while you are setting up a receiver:

```json
{"url": "https://example.com/hooks/vector", "queued": 0, "last_status": 200, "last_error": null}
```

## What the board sends

```
POST /hooks/vector HTTP/1.1
Content-Type: application/json
X-Vector-Signature: 3f1c...e9   (64 hex characters)

{"machine_id": "a1b2c3d4", "type": "end_of_game", "n": 7, "data": {"plays": [["ABC", 1234560], ["XYZ", 980110]], "game_num": 42}}
```

| Field | Meaning |
| --- | --- |
| `machine_id` | The same id as [`/api/machine_id`](routes.md) and Origin messages |
| `type` | One of the events below |
| `n` | Counts up from 1 after every boot. A gap means an event was lost; a repeat can be dropped |
| `data` | Event details, when the event has any |

| `type` | `data` | Sent when |
| --- | --- | --- |
| `reset` | none | The board has started up (usually `n: 1`; a fault raised during boot can come first) |
| `end_of_game` | `plays`: `[initials, score]` for each player who scored; `game_num` | A game ends |
| `fault` | `fault`: the fault text, e.g. `"HDWR02: No Bus Activity"` | A fault is raised |
| `fault_cleared` | `fault`: the fault code, e.g. `"WIFI02"` | A raised fault clears |

The live game state is never sent over a webhook.

## Verifying a request

`X-Vector-Signature` is the hex HMAC-SHA256 of the raw request body, keyed with your secret. Check it before trusting anything in the body:

```python
import hashlib
import hmac


def is_from_my_board(raw_body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

The connection is encrypted, but the board has no certificate store to check your server's certificate against. The signature is what proves a request came from your board.

Because the board does not check the certificate, a device that controls the network path can act as your server. It can read events or stop them. It cannot make or change an event without the secret, and the board never sends the secret. The board also ignores the response body, so a false server cannot control the board.

## Delivery

Delivery is best effort. Events wait in a short queue on the board (4 events; the oldest is dropped when it is full) and are sent one at a time in the background, so a slow server never holds up the game. If a request fails or returns anything other than a 2xx status, the board retries it once about 30 seconds later and then drops it. While the board is off WiFi, events wait in that same queue. A software update drops the events that are waiting.

Reply quickly with any 2xx status; the board ignores the response body.
