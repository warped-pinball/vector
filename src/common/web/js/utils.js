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
