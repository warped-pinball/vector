//
// Generic / Utility functions
//

/**
 * Fetch with automatic retry on failure.
 * On retry attempts a cache-busted URL is used to bypass any stale cache.
 * @param {string} url
 * @param {RequestInit} [opts]
 * @param {number} [maxRetries=2]
 * @returns {Promise<Response>}
 */
async function fetchWithRetry(url, opts, maxRetries) {
  if (maxRetries === undefined) maxRetries = 2;
  var lastError;
  for (var attempt = 0; attempt <= maxRetries; attempt++) {
    var fetchUrl = url;
    if (attempt > 0) {
      // Cache-bust on retries so a stale cached response is not replayed
      var sep = url.indexOf("?") === -1 ? "?" : "&";
      fetchUrl = url + sep + "_r=" + Date.now();
      await new Promise(function (resolve) {
        setTimeout(resolve, attempt * 500);
      });
    }
    try {
      var response = await fetch(fetchUrl, opts);
      return response;
    } catch (err) {
      lastError = err;
      console.warn(
        "fetchWithRetry: attempt " + attempt + " failed for " + url,
        err,
      );
    }
  }
  throw lastError;
}

window.fetchWithRetry = fetchWithRetry;

/**
 * Detect firmware version changes and reload the page when they occur.
 *
 * On every page load this function fetches /api/version with no-store so the
 * server always answers (the response is tiny — just a JSON version string).
 * If the version matches what was last recorded in localStorage the cache is
 * considered fresh and we return immediately — no further network traffic.
 * If the version changed the service worker has already replaced the cache
 * with new assets during its install/activate cycle; all we need to do is
 * reload the page so the updated HTML (and its versioned asset URLs) are used.
 * For browsers without service-worker support the build-time ?v=VERSION query
 * params in the HTML act as cache-busters for the HTTP cache.
 * @returns {Promise<void>}
 */
async function verifyStaticIntegrity() {
  try {
    var versionResponse = await fetchWithRetry("/api/version", {
      cache: "no-store",
    });
    if (!versionResponse.ok) {
      console.warn(
        "verifyStaticIntegrity: version fetch failed",
        versionResponse.status,
      );
      return;
    }
    var versionData = await versionResponse.json();
    var serverVersion = versionData.version;
    var cachedVersion = localStorage.getItem("vv_version");

    if (cachedVersion === serverVersion) {
      return;
    }

    // Record the new version before reloading to avoid an infinite reload loop.
    localStorage.setItem("vv_version", serverVersion);

    if (cachedVersion === null) {
      // First ever visit — assets were just downloaded fresh; no reload needed.
      return;
    }

    // Firmware updated — reload so the page uses the new SW cache / versioned URLs.
    window.location.reload();
  } catch (err) {
    console.warn("verifyStaticIntegrity: error", err);
  }
}

window.verifyStaticIntegrity = verifyStaticIntegrity;

// Run integrity check on every page load
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", verifyStaticIntegrity);
} else {
  verifyStaticIntegrity();
}

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

async function smartFetch(url, data = false, auth = true) {
  console.log({ url, data, auth });
  const headers = {
    "Content-Type": "application/json",
  };
  if (auth) {
    const password = await window.get_password();
    const cRes = await fetchWithRetry("/api/auth/challenge");
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
  const response = await fetchWithRetry(url, {
    method,
    headers,
    body: data ? JSON.stringify(data) : undefined,
  });
  if (auth && response.status === 401) {
    alert("Authentication failed. Please try again.");
    window.logout();
  }
  return response;
}

window.smartFetch = smartFetch;

async function fetchGzip(url) {
  const response = await fetchWithRetry(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  const ds = new DecompressionStream("gzip");
  const decompressed = response.body.pipeThrough(ds);
  return await new Response(decompressed).text();
}

window.fetchGzip = fetchGzip;
