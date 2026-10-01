# Web UI Loading Resilience

## Summary

The web UI (especially the Admin page) sometimes failed to load and did not
recover. The browser showed the header menu and the footer logo, but none of the
page's controls. Clicking the nav link again did nothing. Only a full page
reload helped, and sometimes not even that.

This change hardens loading against dropped WiFi packets and other transient
network problems in three places:

1. **Client fetches have timeouts and retries.** A new `fetchWithTimeout()`
   helper is used by `smartFetch()` and the page loader.
2. **Page navigation is all-or-nothing.** A page's HTML and JS are fully
   downloaded before the current page is torn down. A failure leaves the
   current page in place and shows a Retry message.
3. **The Pico web server no longer leaks connections.** Reading a request is
   time-limited, sending a response is time-limited, and the socket is always
   closed.

## Background: how a page loads

`index.html` is a single-page shell. The header nav, the modals, the footer and
the `<img id="logo">` are static markup. Each page (Scores, Players, About,
Admin) is made of resources listed in `pageConfig` in
[main.js](../src/common/web/js/main.js):

```js
admin: {
  title: "Admin",
  resources: [
    { url: "/html/admin.html", targetId: "page_html" },
    { url: "/js/admin.js", targetId: "page_js" },
  ],
},
```

`handleNavigation(pageKey)` loads those resources into the `page_html` and
`page_js` placeholders. Once `admin.js` runs, it makes about nine separate API
calls (tournament mode, claim methods, show IP, midnight madness, switch
diagnostics, adjustment profiles, Wi‑Fi status, update check, …). Each call
fills in and enables one control.

On first load, `init()` calls `loadLogo()` only after the page navigation
returns. So a visible logo means navigation had already returned, even when it
returned without loading the page.

## Why it failed

### Client side

- **Errors were swallowed and the page was still marked loaded.** If
  `admin.html` failed to download, the error was only logged and `page_html`
  stayed hidden. `currentPageKey` was still set to `"admin"`, so
  `handleNavigation` treated a second click on Admin as "already on this page"
  and ignored it.
- **There were no timeouts.** No `fetch()` used an `AbortController`. A
  half-open TCP connection (lost packets, a phone's WiFi power-save, a stuck
  server task) could leave a request pending for minutes or forever. While
  pending, the `isNavigating` lock stayed set and every nav click was dropped.
- **The old page was removed first.** `clearPreviousResources()` ran *before*
  the new resources were fetched. A stalled request therefore left an empty
  shell: menu and logo, no controls.

### Server side ([phew/server.py](../src/common/phew/server.py))

- **No read timeout.** `reader.readline()` and the header parser could wait
  forever. A client that connected and went quiet kept its task and lwIP TCP
  connection slot (PCB) alive indefinitely, with no TCP keepalive. Examples:
  dropped packets, a sleeping phone, an unused browser preconnect socket.
- **The socket was only closed on the happy path.** The `writer.close()` in the
  `finally` block wrapped only the response-writing code. These paths returned
  or raised without closing the socket:
  - an empty or malformed request line (which is what an unused preconnect
    socket produces);
  - end-of-file in the middle of the headers;
  - an exception from the route handler.
- The Pico W has only a small number of TCP connection slots and a listen
  backlog of 5. Leaked and stalled connections piled up until new connections
  hung or were refused. To the user, the device looked "flaky" until it was
  rebooted.

## Changes

### 1. `fetchWithTimeout()` — [utils.js](../src/common/web/js/utils.js)

A drop-in wrapper around `fetch()`:

```js
fetchWithTimeout(url, options = {}, { timeoutMs = 8000, retries = 2, backoffMs = 500 } = {})
```

How it works:

- **Per-attempt timeout.** Each attempt creates an `AbortController` and starts
  a timer that aborts the request after `timeoutMs`. The timer is cleared as
  soon as `fetch()` resolves, which happens when the response **headers**
  arrive. The timeout therefore covers "is the server responding at all?", not
  how long the body takes. That matters for streamed responses like
  `/api/update/apply`, whose progress stream can legitimately run for minutes.
- **Retries.**
  - Network errors and timeouts are retried.
  - **5xx** responses are retried.
  - Anything else (2xx, 3xx, 4xx) is returned to the caller unchanged. Retrying
    a 401 or 404 would not help.
  - On the last attempt a 5xx response is returned rather than thrown, so
    callers that check `response.ok` behave as before.
- **Backoff with jitter.** Before retry *n* the helper waits
  `backoffMs × 2^(n−1) × (0.5–1.5 random)`, which is about 0.5 s and then
  about 1 s with the defaults. The randomness keeps the ~9 concurrent Admin
  requests from all retrying at the same instant against a server that can
  only accept a few connections.
- **Errors.** If every attempt fails, it throws the last error. A timeout
  becomes a readable `"<url> timed out after <n>ms"` instead of a bare
  `AbortError`.

It is exported as `window.fetchWithTimeout`. `fetchGzip()`, which loads the
logo, now uses it as well.

### 2. `smartFetch()` uses it — [utils.js](../src/common/web/js/utils.js)

`smartFetch` gained an optional fourth argument:

```js
smartFetch(url, data = false, auth = true, { timeoutMs = 15000, retries = null } = {})
```

Existing callers are unchanged and get the defaults.

| Request                         | Timeout | Retries | Why                                                                                                                                           |
| ------------------------------- | ------- | ------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| GET, no auth                    | 15 s    | 2       | Safe to repeat. 15 s allows for the server being briefly busy (it handles one request handler at a time).                                     |
| POST (`data` given)             | 15 s    | 0       | A POST that timed out may already have been applied on the device. Repeating it could apply a change twice.                                   |
| Any request with `auth = true`  | 15 s    | 0       | The HMAC is signed with a single-use challenge, so the same request cannot be resent. The `/api/auth/challenge` request itself *is* retried. |

Two Admin calls override the defaults
([admin.js](../src/common/web/js/admin.js)):

- **`/api/update/check` → `{ timeoutMs: 30000, retries: 0 }`.** The device
  fetches update data from GitHub synchronously, which can take 10 s or more.
  The route also refuses repeat calls for 10 s, so a retry would only get a
  429.
- **`/api/time/trigger_midnight_madness` → `{ retries: 0 }`.** This is a GET
  with a side effect, so it must not be repeated automatically.

> **When adding new calls:** if a GET changes state on the device, pass
> `{ retries: 0 }`. If a route can take longer than 15 s to *start* responding,
> raise `timeoutMs`.

### 3. All-or-nothing navigation — [main.js](../src/common/web/js/main.js)

The old `fetchAndApply()` downloaded and applied each resource in one step. That
is now split into separate steps:

| Function                         | Role                                                                                                                                                            |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fetchPageResource(url)`         | Downloads one resource as text via `fetchWithTimeout` (8 s, 2 retries). Throws on failure or a non-OK status.                                                   |
| `fetchPageResources(pageKey)`    | Downloads all of a page's resources into memory, HTML first then JS, one at a time so the Pico isn't hit with concurrent requests. **Does not touch the DOM.** |
| `applyResource(url, id, text)`   | Puts one downloaded resource into its placeholder.                                                                                                              |
| `applyPageResources(fetched)`    | Clears the previous page's resources, then applies the new ones, HTML before JS.                                                                                |
| `loadPageResources(pageKey)`     | Kept for debugging from the console: fetch, then apply.                                                                                                         |

`handleNavigation()` now runs in this order:

```
isNavigating = true
try:
    resources = await fetchPageResources(pageKey)   ← all network I/O happens here
    run cleanup_<currentPage>()                      ← only after everything arrived
    push/replace history entry
    clear any error banner
    applyPageResources(resources)                    ← synchronous swap
    currentPageKey = pageKey
catch:
    show "Couldn't load <title>… Retry" banner       ← current page left as-is
finally:
    isNavigating = false
    set_game_name()                                  ← errors caught and logged
```

What this guarantees:

- **The current page is never replaced by an empty shell.** If any resource
  fails or times out, nothing in the DOM has changed yet. The user still sees
  the page they were on, with the error banner above it. On first load there
  is no previous page, so the banner appears on its own.
- **Failures can always be retried.** `currentPageKey` is only updated on
  success. Clicking the nav link again, or pressing **Retry**, makes a fresh
  attempt instead of being dropped as "already on this page".
- **The lock can't stick.** Every fetch is time-limited, so `isNavigating` is
  always released. Worst case is about 3 attempts × 8 s plus backoff per
  resource.
- **History matches what is on screen.** The URL (`/?page=…`) is only pushed
  after a successful load. On a failed nav click the URL keeps pointing at the
  page that is still showing.

#### The error banner

`showPageLoadError(title, retry)` creates (or reuses) an
`<article id="page_error">` just before `page_html` inside `<main>`. It holds a
message and a **Retry** button. Retry disables the button, sets
`aria-busy="true"` on it (Pico CSS shows a spinner) and calls
`handleNavigation` again with the same arguments.

The banner is removed by `clearPageLoadError()` in these cases:

- a navigation succeeds;
- the user clicks the nav link for the page already showing.

If the retry fails again, the banner is redrawn with an enabled button.

#### Scripts are now inserted inline

Page scripts used to be injected as `<script src="/js/admin.js">`, which
triggered a *second*, unprotected download. Because the JS has already been
downloaded (with timeout and retry), it is now inserted as an inline script:

```js
script.textContent = text + "\n//# sourceURL=" + url;
```

- Inline scripts run synchronously when inserted. The page's top-level code has
  run, and registered any `cleanup_<page>` hook, before navigation is reported
  complete. The old code needed an `onload` promise for that.
- The `//# sourceURL=` comment makes DevTools list the code under its real file
  name (`/js/admin.js`) for breakpoints and stack traces.
- The string is built with plain concatenation instead of a template literal,
  so the `//` cannot be mistaken for a comment by the `jsmin` step in
  `dev/build.py`.
- Page scripts are re-run each time the page is entered, same as before. They
  must not declare top-level `let`, `const` or `class`, which would throw
  "already declared" the second time. None currently do.

### 4. Server: request timeouts and guaranteed close — [phew/server.py](../src/common/phew/server.py)

Request reading moved into a new coroutine:

```python
async def _read_request(reader):
    # request line → Request object (None if empty/malformed)
    # headers
    # JSON body (if Content-Type: application/json)
```

`_handle_request` now looks like this:

```python
async def _handle_request(reader, writer):
    try:
        request = await uasyncio.wait_for_ms(_read_request(reader), _REQUEST_READ_TIMEOUT_MS)
        if request is None:
            return                       # empty preconnect / garbage → just close
        ... route lookup, handler(request), build response ...
        ... write status line + headers ...
        await uasyncio.wait_for_ms(writer.drain(), _RESPONSE_DRAIN_TIMEOUT_MS)   # per chunk
    except Exception as e:
        logging.error(...)
    finally:
        writer.close()                   # every path, no exceptions
        await writer.wait_closed()
```

How each part works:

- **Read timeout (`_REQUEST_READ_TIMEOUT_MS = 10000`).** The request line,
  headers and body must all arrive within 10 s in total. On timeout,
  `wait_for_ms` cancels the read and raises. The `except` logs it and the
  `finally` closes the socket. 10 s is far longer than a healthy request needs,
  even with several TCP retransmits, and short enough that a stalled client
  frees its slot quickly.
- **Write timeout (`_RESPONSE_DRAIN_TIMEOUT_MS = 10000`).** Every
  `writer.drain()` is limited to 10 s. That covers the plain-body path and each
  1 KB chunk of a streamed body (static files, update progress). If the client
  disappears mid-response, the task gives up after 10 s instead of waiting
  through lwIP's retransmission backoff, which can take minutes.
- **Guaranteed close.** The `try/finally` now wraps the whole handler, so the
  socket is closed on every path:
  - a normal response;
  - an empty or malformed request (no longer logged, since empty preconnect
    sockets are routine);
  - end-of-file mid-headers or a read timeout;
  - a route handler that raises;
  - a dropped connection or write timeout mid-stream (still logged as
    "Truncated streamed response for …").
- **USB is unaffected.** The USB transport
  ([usb_comms.py](../src/common/usb_comms.py)) builds its own `Request` and
  calls route handlers directly. It never goes through `_handle_request`.

Both timeouts are `const()` values at module level, next to `_read_request`.

## Verification

- **Server logic.** `_handle_request` was run under CPython with `uasyncio`
  shimmed to `asyncio` and the device modules stubbed. The test cases were:
  - a normal GET;
  - a JSON POST;
  - an empty preconnect (end-of-file);
  - a garbage request line;
  - end-of-file mid-headers;
  - a client that stalls mid-headers;
  - a client that stalls before sending anything;
  - a handler that raises.

  The new code closes the socket in every case, and the two stalled clients
  are released at the timeout. The previous code hung forever on the
  stalled-client case.
- **JavaScript.** The edited files parse, both as written and after `jsmin`
  minification.
- **On device.** Smoke-tested on hardware: the UI loads and runs normally.
  The failure paths (timeouts, retries, error banner) have not yet been
  exercised on a device. See below.

### Testing transient failures manually

In Chrome DevTools → Network:

1. Load the Scores page, set throttling to **Offline**, and click **Admin**.
   After the retries run out (about 25 s), the Scores page should still be
   showing, with a "Couldn't load Admin" banner above it. The nav should keep
   working.
2. Set throttling back to **No throttling** and click **Retry**. Admin should
   load and the banner should disappear.
3. Repeat from a fresh `/?page=admin` load while offline. The banner should
   appear on its own, and Retry should recover once back online.
4. To simulate a slow, lossy link, use a custom throttling profile with high
   latency (for example 3000 ms) and confirm pages still load, just more
   slowly.

## Not covered by this change

Follow-ups from the same investigation, not yet implemented:

- **Admin controls don't retry individually.** Each initializer in `admin.js`
  now benefits from `smartFetch` retries. If all attempts fail, though, that
  control still stays silently disabled. A per-control "Unavailable – retry"
  state would need the event-listener binding separated from the data loading,
  because `populateAdjustmentProfiles()` already adds duplicate listeners each
  time it re-runs.
- **`Connection: close` is only sent on static files.** The server always
  closes after one response, but API responses don't say so. The browser may
  then try to reuse a socket the Pico is closing.
- **304 responses inherit `Cache-Control: no-store`.** These come from
  `route_wrapper`'s defaults and effectively make an asset uncacheable once it
  has been revalidated.
- **Static assets have no cache-busting.** They are served `immutable` for a
  year with no version in the URL, so stale JS or HTML can survive a firmware
  update.
- **`/api/update/check` blocks the event loop.** It does a synchronous GitHub
  fetch, during which no other request is served.
- **Some calls still use bare `fetch()`.** These are in `configure.js`,
  `install_warning.js` and `scores.js`.
