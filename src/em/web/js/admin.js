// ------------------ Setup / Sensitivity Helpers ------------------

// Helper: show modal by id
async function showModal(id) {
  const modal = document.getElementById(id);
  if (!modal) return null;
  if (typeof modal.showModal === "function") modal.showModal();
  return modal;
}

// Initialize Setup UI values and listeners
async function initSetupUI() {
  // load existing settings if the API exists
  let serverCfgLoaded = false;
  try {
    const resp = await window.smartFetch("/api/em/get_config", null, false);
    if (resp.ok) {
      const cfg = await resp.json();
      const name = document.getElementById("game-name");
      const players = document.getElementById("total-players");
      const reels = document.getElementById("score-reels");
      const dummy = document.getElementById("dummy-reels");
      // support both server field names
      if (name && (cfg.name || cfg.game_name)) {
        name.value = cfg.name || cfg.game_name || "";
      }
      if (players && (cfg.total_players != null || cfg.players != null)) {
        // server may return 'players' or 'total_players'
        players.value = Number(cfg.total_players ?? cfg.players) || 0;
      }
      if (reels && (cfg.score_reels != null || cfg.reels_per_player != null)) {
        reels.value = Number(cfg.score_reels ?? cfg.reels_per_player) || 0;
      }
      if (dummy && cfg.dummy_reels != null)
        dummy.value = Number(cfg.dummy_reels) || 0;
      serverCfgLoaded = true;
    }
  } catch (e) {
    // ignore if endpoint not available
  }

  // add listeners to inputs to save locally
  const inputs = ["game-name", "total-players", "score-reels", "dummy-reels"];
  inputs.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener("change", () => {
      const data = {
        name: document.getElementById("game-name").value,
        total_players:
          parseInt(document.getElementById("total-players").value, 10) || 1,
        score_reels:
          parseInt(document.getElementById("score-reels").value, 10) || 1,
        dummy_reels:
          parseInt(document.getElementById("dummy-reels").value, 10) || 0,
      };
      try {
        localStorage.setItem("game_config", JSON.stringify(data));
      } catch (e) {}
      // show save button when user changes any config input
      const saveBtn = document.getElementById("save-game-config");
      if (saveBtn) saveBtn.style.display = "";
    });
  });

  // populate from localStorage if available and server did not provide config
  try {
    const stored = JSON.parse(localStorage.getItem("game_config") || "null");
    if (stored && !serverCfgLoaded) {
      document.getElementById("game-name").value = stored.name || "";
      document.getElementById("total-players").value =
        stored.total_players || 1;
      document.getElementById("score-reels").value = stored.score_reels || 1;
      document.getElementById("dummy-reels").value = stored.dummy_reels || 0;
    }
  } catch (e) {}
}


async function loadConfiguredSsidSignal() {
  const nameElement = document.getElementById("configured-ssid-name");
  const rssiElement = document.getElementById("configured-ssid-rssi");
  const qualityElement = document.getElementById("configured-ssid-quality");

  if (!nameElement || !rssiElement || !qualityElement) {
    return;
  }

  try {
    const response = await window.smartFetch("/api/wifi/status", null, false);
    if (!response.ok) {
      throw new Error(`ssid fetch failed: ${response.status}`);
    }
    const data = await response.json();
    if (!data.connected) {
      nameElement.innerText = "Not connected";
      rssiElement.innerText = "Unavailable";
      qualityElement.innerText = "Unavailable";
      return;
    }

    nameElement.innerText = data.ssid ?? "Unknown SSID";
    if (typeof data.rssi === "number") {
      rssiElement.innerText = `${data.rssi} dBm`;
      if (data.rssi >= -60) {
        qualityElement.innerText = "Excellent";
      } else if (data.rssi >= -70) {
        qualityElement.innerText = "Good";
      } else if (data.rssi >= -80) {
        qualityElement.innerText = "Fair";
      } else {
        qualityElement.innerText = "Poor";
      }
    } else {
      rssiElement.innerText = "Unknown";
      qualityElement.innerText = "Unknown";
    }
  } catch (error) {
    console.error("Failed to load configured SSID signal strength", error);
    nameElement.innerText = "Unavailable";
    rssiElement.innerText = "Unavailable";
    qualityElement.innerText = "Unavailable";
  }
}

// Save game configuration to server (calls existing endpoint if available)
async function saveGameConfig() {
  const data = {
    name: document.getElementById("game-name").value,
    players: parseInt(document.getElementById("total-players").value, 10) || 1,
    reels_per_player:
      parseInt(document.getElementById("score-reels").value, 10) || 1,
    dummy_reels:
      parseInt(document.getElementById("dummy-reels").value, 10) || 0,
  };

  try {
    const resp = await window.smartFetch("/api/em/set_config", data, true);
    if (!resp.ok) throw new Error("save failed");
    const saveBtn = document.getElementById("save-game-config");
    if (saveBtn) saveBtn.style.display = "none";
  } catch (e) {
    console.error("Failed to save game configuration", e);
    alert("Failed to save game configuration");
  }
}

// ------------------ Sensitivity Controls ------------------

// Sensitivity: 1–100%
const SENSITIVITY_MIN = 1;
const SENSITIVITY_MAX = 100;
const SENSITIVITY_STEP = 1;
const SENSITIVITY_DEFAULT = 50;

// Timing sensitivity: decade columns in descending order, value range 1–16
const TIMING_ADJ_LABELS = ["10000s", "1000s", "100s", "10s", "1s"];
const TIMING_ADJ_DEFAULT_SCORE = 8;
const TIMING_ADJ_DEFAULT_RESET = 8;
const TIMING_ADJ_MIN = 1;
const TIMING_ADJ_MAX = 16;

// Build an adjuster group element (label, up button, value display, down button)
// colorClass: "score" (red), "reset" (blue), or "" for plain
function buildAdjGroup(label, value, colorClass, onUp, onDown) {
  const group = document.createElement("div");
  group.className = "adj-group";

  const lbl = document.createElement("div");
  lbl.className = "adj-group-label";
  lbl.textContent = label;

  const btnClass = "secondary adj-btn" + (colorClass ? " adj-btn-" + colorClass : "");
  const valClass = "adj-value" + (colorClass ? " adj-val-" + colorClass : "");

  const upBtn = document.createElement("button");
  upBtn.className = btnClass;
  upBtn.textContent = "\u25b2";
  upBtn.addEventListener("click", onUp);

  const valDisplay = document.createElement("div");
  valDisplay.className = valClass;
  valDisplay.textContent = String(value);

  const downBtn = document.createElement("button");
  downBtn.className = btnClass;
  downBtn.textContent = "\u25bc";
  downBtn.addEventListener("click", onDown);

  group.appendChild(lbl);
  group.appendChild(upBtn);
  group.appendChild(valDisplay);
  group.appendChild(downBtn);

  return { group, valDisplay };
}

// Global sensitivity (0â€“100%)
async function initSensitivityUI() {
  let value = SENSITIVITY_DEFAULT;

  try {
    const resp = await window.smartFetch("/api/em/get_sensitivity", null, false);
    if (resp && resp.ok) {
      const data = await resp.json();
      if (data.sensitivity != null) value = Math.min(SENSITIVITY_MAX, Math.max(SENSITIVITY_MIN, Number(data.sensitivity)));
    }
  } catch (e) {
    // use default
  }

  const display = document.getElementById("sensitivity-value");
  const upBtn = document.getElementById("sensitivity-up");
  const downBtn = document.getElementById("sensitivity-down");

  function updateDisplay() {
    if (display) display.textContent = value + "%";
  }

  async function saveSensitivity() {
    try {
      await window.smartFetch("/api/em/set_sensitivity", { sensitivity: value }, true);
    } catch (e) {
      console.error("Failed to save sensitivity", e);
    }
  }

  if (upBtn) {
    upBtn.addEventListener("click", async () => {
      if (value < SENSITIVITY_MAX) {
        value = Math.min(SENSITIVITY_MAX, value + SENSITIVITY_STEP);
        updateDisplay();
        await saveSensitivity();
      }
    });
  }

  if (downBtn) {
    downBtn.addEventListener("click", async () => {
      if (value > SENSITIVITY_MIN) {
        value = Math.max(SENSITIVITY_MIN, value - SENSITIVITY_STEP);
        updateDisplay();
        await saveSensitivity();
      }
    });
  }

  updateDisplay();
}

// Timing filter: per-decade score (red) and reset (blue) depth adjusters, 1–16
// p1_score/p1_reset = Player 1 depths; p2_score/p2_reset = Player 2 depths
async function initTimingSensitivityUI() {
  const N = TIMING_ADJ_LABELS.length;
  let p1_score = Array(N).fill(TIMING_ADJ_DEFAULT_SCORE);
  let p1_reset = Array(N).fill(TIMING_ADJ_DEFAULT_RESET);
  let p2_score = Array(N).fill(TIMING_ADJ_DEFAULT_SCORE);
  let p2_reset = Array(N).fill(TIMING_ADJ_DEFAULT_RESET);

  try {
    const resp = await window.smartFetch("/api/em/get_timing_sensitivity", null, false);
    if (resp && resp.ok) {
      const data = await resp.json();
      if (Array.isArray(data.p1_score) && data.p1_score.length === N) p1_score = data.p1_score.map(Number);
      if (Array.isArray(data.p1_reset) && data.p1_reset.length === N) p1_reset = data.p1_reset.map(Number);
      if (Array.isArray(data.p2_score) && data.p2_score.length === N) p2_score = data.p2_score.map(Number);
      if (Array.isArray(data.p2_reset) && data.p2_reset.length === N) p2_reset = data.p2_reset.map(Number);
    }
  } catch (e) {
    // use defaults
  }

  async function saveTimingSensitivity() {
    try {
      await window.smartFetch("/api/em/set_timing_sensitivity",
        { p1_score, p1_reset, p2_score, p2_reset }, true);
    } catch (e) {
      console.error("Failed to save timing sensitivity", e);
    }
  }

  function buildPlayerRow(containerId, scoreArr, resetArr) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = "";

    TIMING_ADJ_LABELS.forEach((label, i) => {
      const col = document.createElement("div");
      col.className = "decade-col";

      const colLbl = document.createElement("div");
      colLbl.className = "decade-col-label";
      colLbl.textContent = label;
      col.appendChild(colLbl);

      // Red adjuster — score (detection) depth
      const { group: sg, valDisplay: sv } = buildAdjGroup(
        "Score", scoreArr[i], "score",
        async () => {
          if (scoreArr[i] < TIMING_ADJ_MAX) {
            scoreArr[i] = Math.min(TIMING_ADJ_MAX, scoreArr[i] + 1);
            sv.textContent = String(scoreArr[i]);
            await saveTimingSensitivity();
          }
        },
        async () => {
          if (scoreArr[i] > TIMING_ADJ_MIN) {
            scoreArr[i] = Math.max(TIMING_ADJ_MIN, scoreArr[i] - 1);
            sv.textContent = String(scoreArr[i]);
            await saveTimingSensitivity();
          }
        }
      );
      col.appendChild(sg);

      // Blue adjuster — reset (hold-off) depth
      const { group: rg, valDisplay: rv } = buildAdjGroup(
        "Reset", resetArr[i], "reset",
        async () => {
          if (resetArr[i] < TIMING_ADJ_MAX) {
            resetArr[i] = Math.min(TIMING_ADJ_MAX, resetArr[i] + 1);
            rv.textContent = String(resetArr[i]);
            await saveTimingSensitivity();
          }
        },
        async () => {
          if (resetArr[i] > TIMING_ADJ_MIN) {
            resetArr[i] = Math.max(TIMING_ADJ_MIN, resetArr[i] - 1);
            rv.textContent = String(resetArr[i]);
            await saveTimingSensitivity();
          }
        }
      );
      col.appendChild(rg);

      container.appendChild(col);
    });
  }

  buildPlayerRow("timing-adj-p1", p1_score, p1_reset);
  buildPlayerRow("timing-adj-p2", p2_score, p2_reset);
}


//
// Settings
//

// Tournament Mode
async function tournamentModeToggle() {
  const response = await window.smartFetch(
    "/api/settings/get_tournament_mode",
    null,
    false,
  );
  const data = await response.json();

  const tournamentModeToggle = await window.waitForElementById(
    "tournament-mode-toggle",
  );

  tournamentModeToggle.checked = data["tournament_mode"];
  tournamentModeToggle.disabled = false;

  // add event listener to update the setting when the checkbox is changed
  tournamentModeToggle.addEventListener("change", async () => {
    const data = { tournament_mode: tournamentModeToggle.checked ? 1 : 0 };
    await window.smartFetch("/api/settings/set_tournament_mode", data, true);
  });
}

// Score claim methods
async function getScoreClaimMethods() {
  const response = await window.smartFetch(
    "/api/settings/get_claim_methods",
    null,
    false,
  );
  const data = await response.json();

  const webUIToggle = await window.waitForElementById("web-ui-toggle");

  webUIToggle.checked = data["web-ui"];
  webUIToggle.disabled = false;

  // Helper function to add event listener to claim method toggle
  function addClaimMethodToggleListener(toggle) {
    toggle.addEventListener("change", async () => {
      const data = {
        "web-ui": webUIToggle.checked ? 1 : 0,
      };
      await window.smartFetch("/api/settings/set_claim_methods", data, true);
    });
  }

  addClaimMethodToggleListener(webUIToggle);
}

tournamentModeToggle();
getScoreClaimMethods();
initSetupUI();
initSensitivityUI();
initTimingSensitivityUI();
startSensorActivityPolling();

// wire save button
const saveGameConfigBtn = document.getElementById("save-game-config");
if (saveGameConfigBtn) {
  saveGameConfigBtn.style.display = "none";
  saveGameConfigBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    await saveGameConfig();
  });
}

// Sensor activity indicator lamp — polls /api/em/sensor_activity at ~5 Hz
function startSensorActivityPolling() {
  const lamp = document.getElementById("sensor-activity-lamp");
  if (!lamp) return;

  const POLL_MS = 200;      // poll interval
  const LIT_MS  = 500;      // how long to stay green after a hit
  let litUntil  = 0;

  async function poll() {
    try {
      const resp = await window.smartFetch("/api/em/sensor_activity", null, false);
      if (resp && resp.ok) {
        const data = await resp.json();
        if (data.active) litUntil = Date.now() + LIT_MS;
      }
    } catch (e) {
      // ignore — lamp just stays dark
    }
    lamp.style.background = Date.now() < litUntil ? "#2ecc71" : "#444";
    setTimeout(poll, POLL_MS);
  }

  poll();
}

//
// Actions
//

// Download Logs
window.downloadLogs = async function () {
  console.log("Downloading logs...");

  // Perform the fetch (no auth needed if your endpoint doesn't require it)
  const response = await window.smartFetch("/api/logs", null, true);

  if (!response.ok) {
    console.error(
      "Failed to download logs:",
      response.status,
      response.statusText,
    );
    alert("Failed to download logs.");
    return;
  }

  // Get the response as a blob
  const blob = await response.blob();

  // Generate a filename similar to how you do CSVs (with game name, date, etc.)
  let filename = document.getElementById("game_name").innerText;
  filename += "_log_";
  filename += new Date().toISOString().split("T")[0];
  filename += ".txt";

  // Replace spaces with underscores
  filename = filename.replace(/ /g, "_");

  // Create a temporary link to trigger the download
  const url = window.URL.createObjectURL(blob);
  const element = document.createElement("a");
  element.href = url;
  element.download = filename;
  document.body.appendChild(element);
  element.click();

  // Clean up
  document.body.removeChild(element);
  window.URL.revokeObjectURL(url);

  console.log("Logs download initiated.");
};

// Download Memory Snapshot
window.downloadMemorySnapshot = async function () {
  console.log("Downloading memory snapshot...");

  // Perform the fetch (no auth needed if your endpoint doesn't require it)
  const response = await window.smartFetch("/api/memory-snapshot", null, false);

  if (!response.ok) {
    console.error(
      "Failed to fetch memory snapshot:",
      response.status,
      response.statusText,
    );
    alert("Failed to download memory snapshot.");
    return;
  }

  // Get the response as text
  const content = await response.text();

  // Generate a filename similar to how you do CSVs
  let filename = document.getElementById("game_name").innerText;
  filename += "_memory_";
  filename += new Date().toISOString().split("T")[0];
  filename += ".txt";

  // Replace spaces with underscores
  filename = filename.replace(/ /g, "_");

  // Create a temporary link to trigger the download
  const element = document.createElement("a");
  element.href = "data:text/plain;charset=utf-8," + encodeURIComponent(content);
  element.download = filename;
  document.body.appendChild(element);
  element.click();

  // Clean up
  document.body.removeChild(element);

  console.log("Memory snapshot download initiated.");
};

// Download Scores
window.downloadScores = async function () {
  console.log("Downloading scores...");

  const response = await window.smartFetch("/api/export/scores", null, false);

  if (!response.ok) {
    console.error(
      "Failed to download scores:",
      response.status,
      response.statusText,
    );
    alert("Failed to download scores.");
    return;
  }

  // Get the response
  const data = await response.json();

  // Generate a filename similar to how you do CSVs (with game name, date, etc.)
  let filename = document.getElementById("game_name").innerText;
  filename += "_scores_";
  filename += new Date().toISOString().split("T")[0];
  filename += ".json";

  // Replace spaces with underscores
  filename = filename.replace(/ /g, "_");

  // Create a temporary link to trigger the download
  const element = document.createElement("a");
  element.href =
    "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(data));
  element.download = filename;
  document.body.appendChild(element);
  element.click();

  // Clean up
  document.body.removeChild(element);

  console.log("Scores download initiated.");
};

// Download Diagnostic Data
window.downloadDiagnostics = async function () {
  console.log("Downloading diagnostics...");
  try {
    const resp = await window.smartFetch("/api/em/diagnostics", null, true);
    if (!resp) throw new Error("No response");

    // The backend returns plain text. If resp is a Response-like object try text(),
    // otherwise treat it as a direct string.
    let content = "";
    try {
      // Some environments return a Response instance
      if (resp.text) {
        content = await resp.text();
      } else if (typeof resp === "string") {
        content = resp;
      } else {
        content = JSON.stringify(resp, null, 2);
      }
    } catch (e) {
      // fallback
      content = String(resp);
    }

    const filename =
      "diagnostics_" + new Date().toISOString().split("T")[0] + ".txt";
    const blob = new Blob([content], { type: "text/plain" });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);

    console.log("Diagnostics download initiated.");
  } catch (e) {
    console.error("Failed to download diagnostics:", e);
    alert("Failed to download diagnostics.");
  }
};

//
// Updates
//

async function checkForUpdates() {
  // wait 1 second before checking for updates
  // this lets us prioritize loading the page and settings
  await new Promise((resolve) => setTimeout(resolve, 1000));

  try {
    const response = await window.smartFetch("/api/update/check", null, false);
    if (!response.ok) {
      throw new Error(`update check failed: ${response.status}`);
    }

    let data;
    try {
      data = await response.json();
    } catch (jsonError) {
      console.error("Invalid JSON in update check response", jsonError);
      throw jsonError;
    }

    console.debug("Update check response data:", data);

    const updateButton = document.getElementById("update-button");

    if (!updateButton) {
      console.log("No update button found, must have left page");
      return;
    }

    // get the current version from the page
    const current = document
      .getElementById("version")
      .textContent.split(" ")[1];

    // link to release notes in text
    const releaseNotes = document.getElementById("release-notes");
    const releaseLink = document.getElementById("release-link");
    if (releaseNotes) {
      if (data["release_page"]) {
        releaseLink.href = data["release_page"];
        releaseLink.textContent = `GitHub release for ${
          data["version"] || "unknown version"
        }`;
        releaseLink.classList.remove("hide");
      } else {
        releaseLink.classList.add("hide");
      }

      if (data["notes"]) {
        releaseNotes.innerHTML = data["notes"];
        releaseNotes.classList.remove("hide");
      } else {
        releaseNotes.classList.add("hide");
      }
    }

    // if the latest is equal to the current version we are up to date
    if (data["version"] === current) {
      updateButton.classList.remove("golden-button");
      updateButton.textContent = "Already up to date";
      updateButton.disabled = true;
    } else {
      // there is an update with an update.json asset

      // update available
      updateButton.disabled = false;
      updateButton.classList.add("golden-button");
      updateButton.textContent = `Update to ${data["version"]}`;

      // get the url for the update.json asset and add an event listener to the button
      const update_url = data["url"];

      // define the call back function to apply the update
      const callback = async () => {
        await applyUpdate(update_url);
      };

      updateButton.addEventListener("click", async () => {
        await confirmAction("update to version: " + data["version"], callback);
      });
    }
  } catch (e) {
    console.error("Failed to check for updates:", e);
    const updateButton = document.getElementById("update-button");
    if (updateButton) {
      updateButton.textContent = "Could not get updates";
      updateButton.disabled = true;
      updateButton.title = e.message || e.toString();
    }
  }
}

async function applyUpdate(url, skip_signature_check = false) {
  const req_data = { url: url, skip_signature_check: skip_signature_check };
  const response = await window.smartFetch("/api/update/apply", req_data, true);
  if (!response.ok) {
    throw new Error("Failed to start update");
  }

  const updateModal = document.getElementById("update-progress-modal");
  updateModal.showModal();

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  const progressBar = document.getElementById("update-progress-bar");
  const updateProgressLog = document.getElementById("update-progress-log");

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      let msg = decoder.decode(value, { stream: true });

      msg = msg.split("}{");
      for (let i = 0; i < msg.length; i++) {
        if (i !== 0) {
          msg[i] = "{" + msg[i];
        }
        if (i !== msg.length - 1) {
          msg[i] = msg[i] + "}";
        }
      }

      for (let i = 0; i < msg.length; i++) {
        const msg_obj = JSON.parse(msg[i]);

        if (msg_obj.log) {
          updateProgressLog.textContent += msg_obj.log + "\n";
        }
        if (msg_obj.percent) {
          progressBar.value = msg_obj.percent;
        }
      }

      // scroll to the bottom of the log
      updateProgressLog.scrollTop = updateProgressLog.scrollHeight;
    }
  } catch (e) {
    // if progress bar is at 100% then the update was successful and the server has just rebooted
    if (progressBar.value === 100) {
      // refresh the page
      window.location.reload();
    } else {
      updateProgressLog.textContent += "Connection lost.\n";
      updateProgressLog.textContent += "Refresh the page and Try again.\n";
      progressBar.value = 0;
      return;
    }
  }

  if (response.status !== 200) {
    updateProgressLog.textContent += "Failed to apply update.\n";
    updateProgressLog.textContent += "Status: " + response.status + "\n";
    updateProgressLog.textContent +=
      "Status Text: " + response.statusText + "\n";
  }
}

checkForUpdates();
window.applyUpdate = applyUpdate;

// custom update function
window.customUpdate = async function () {
  // prompt the user for the update url
  const url = prompt("Enter the URL for the update");
  if (url === null) {
    return;
  }
  // confirm url
  await confirmAction(
    "Do you trust the source of this update and want to apply the update file at the url: " +
      url,
    async () => {
      await window.applyUpdate(url, true);
    },
  );
};

loadConfiguredSsidSignal();
