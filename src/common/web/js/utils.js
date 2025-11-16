//
// Generic / Utility functions
//

const { call, pass } = require("three/tsl");

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
    const cRes = await fetch("/api/auth/challenge");
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
  const response = await fetch(url, {
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
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status}`);
  }
  const ds = new DecompressionStream("gzip");
  const decompressed = response.body.pipeThrough(ds);
  return await new Response(decompressed).text();
}

window.fetchGzip = fetchGzip;
