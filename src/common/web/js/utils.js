//
// Generic / Utility functions
//

async function confirm_auth_get(
  url,
  purpose,
  data = null,
  callback = null,
  cancelCallback = null,
) {
  return await confirmAction(
    purpose,
    async () => {
      const response = await window.smartFetch(url, data, true);
      if (response.status !== 200 && response.status !== 401) {
        // 401 already alerted the user that their password was wrong
        console.error(`Failed to ${purpose}:`, response.status);
        alert(`Failed to ${purpose}.`);
      }
      if (callback != undefined) {
        callback(response);
      }
    },
    () => {
      //Cancelled
      if (cancelCallback != undefined) {
        cancelCallback();
      }
    },
  );
}

async function confirmAction(message, callback, cancelCallback = null) {
  const modal = await window.waitForElementById("confirm-modal");
  const modalMessage = await window.waitForElementById("modal-message");
  const confirmButton = await window.waitForElementById("modal-confirm-button");
  const cancelButton = await window.waitForElementById("modal-cancel-button");

  modalMessage.textContent = `Are you sure you want to ${message}?`;

  confirmButton.onclick = () => {
    modal.close();
    callback();
  };

  cancelButton.onclick = () => {
    modal.close();
    if (cancelCallback) {
      cancelCallback();
    }
  };

  modal.showModal();
}

// fetch() with a per-attempt timeout and retries, for a Pico server on WiFi
// where packets get dropped and connections occasionally go half-open.
// The timeout covers the wait for response headers only (so long streamed
// bodies like update progress aren't cut off). Retries happen on network
// errors, timeouts and 5xx responses; 4xx responses are returned as-is.
// Only pass retries > 0 for requests that are safe to repeat.
async function fetchWithTimeout(
  url,
  options = {},
  { timeoutMs = 8000, retries = 2, backoffMs = 500 } = {},
) {
  let lastError = null;
  for (let attempt = 0; attempt <= retries; attempt++) {
    if (attempt > 0) {
      // exponential backoff with jitter so concurrent retries spread out
      const delay = backoffMs * 2 ** (attempt - 1) * (0.5 + Math.random());
      await new Promise((resolve) => setTimeout(resolve, delay));
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      if (response.status >= 500 && attempt < retries) {
        lastError = new Error(`${url} returned ${response.status}`);
        console.warn(`${lastError.message}, retrying`);
        continue;
      }
      return response;
    } catch (error) {
      lastError =
        error.name === "AbortError"
          ? new Error(`${url} timed out after ${timeoutMs}ms`)
          : error;
      console.warn(
        `Fetch attempt ${attempt + 1}/${retries + 1} failed for ${url}:`,
        lastError,
      );
    } finally {
      clearTimeout(timer);
    }
  }
  throw lastError;
}

window.fetchWithTimeout = fetchWithTimeout;

async function smartFetch(
  url,
  data = false,
  auth = true,
  { timeoutMs = 15000, retries = null } = {},
) {
  console.log({ url, data, auth });
  // GETs are retried by default; POSTs are not, since a timed-out POST may
  // already have been applied on the device.
  if (retries === null) {
    retries = data ? 0 : 2;
  }
  const headers = {
    "Content-Type": "application/json",
  };
  if (auth) {
    const password = await window.get_password();
    const cRes = await fetchWithTimeout("/api/auth/challenge");
    if (!cRes.ok) throw new Error("Failed to get challenge.");
    const { challenge } = await cRes.json();
    const urlObj = new URL(url, window.location.origin);
    const data_str = data ? JSON.stringify(data) : "";
    const msg = challenge + urlObj.pathname + urlObj.search + data_str;
    const hmacHex = sha256.hmac(password, msg);
    headers["X-Auth-HMAC"] = hmacHex;
    headers["X-Auth-challenge"] = challenge;
  }
  const method = data ? "POST" : "GET";
  // An authenticated request's challenge is single-use, so it can't be
  // resent as-is; retry it by calling smartFetch again instead.
  const response = await fetchWithTimeout(
    url,
    {
      method,
      headers,
      body: data ? JSON.stringify(data) : undefined,
    },
    { timeoutMs, retries: auth ? 0 : retries },
  );
  if (auth && response.status === 401) {
    alert("Authentication failed. Please try again.");
    window.logout();
  }
  return response;
}

window.smartFetch = smartFetch;

async function fetchGzip(url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  const ds = new DecompressionStream("gzip");
  const decompressed = response.body.pipeThrough(ds);
  return await new Response(decompressed).text();
}

window.fetchGzip = fetchGzip;
