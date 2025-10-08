//
// Generic / Utility functions
//

async function confirm_auth_get(url, purpose) {
  await confirmAction(purpose, async () => {
    const response = await window.smartFetch(url, null, true);
    if (response.status !== 200 && response.status !== 401) {
      // 401 already alerted the user that their password was wrong
      console.error(`Failed to ${purpose}:`, response.status);
      alert(`Failed to ${purpose}.`);
    }
  });
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

// ------------------ Setup / Calibration Helpers ------------------

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

// Configurable threshold for switching messages (percent)
// Change this value to adjust when the UI prompts the user to allow the ball to drain
const CALIBRATION_MESSAGE_THRESHOLD = 80;
// Minimum number of recorded games required to allow starting the learning process
const CALIBRATION_MIN_GAMES_REQUIRED = 1;

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

// Delete all calibration games (calls API and refreshes UI)
window.deleteCalibrationGames = async function () {
  await confirmAction("delete all stored calibration games", async () => {
    try {
      const resp = await window.smartFetch(
        "/api/em/delete_calibration_games",
        null,
        true,
      );
      if (!resp.ok) throw new Error("delete failed");
      refreshRecordedGamesCount();
    } catch (e) {
      console.error("Failed to delete calibration games", e);
      alert("Failed to delete calibration games");
    }
  });
};

// Fetch recorded games count and update the UI. Enables start button only when count === total
async function refreshRecordedGamesCount() {
  try {
    const resp = await window.smartFetch(
      "/api/em/recorded_games_count",
      null,
      false,
    );
    if (!resp.ok) return;
    const data = await resp.json();
    const status = document.getElementById("recorded-games-status");
    const startBtn = document.getElementById("start-learning");
    if (status)
      status.textContent = `Recorded: ${data.count || 0}/${data.total || 4}`;
    if (startBtn) {
      // enable start when at least the minimum number of games have been recorded
      if ((data.count || 0) >= CALIBRATION_MIN_GAMES_REQUIRED) {
        startBtn.disabled = false;
      } else {
        startBtn.disabled = true;
      }
    }
  } catch (e) {
    console.error("Failed to refresh recorded games count", e);
  }
}

// Start recording a calibration game - opens modal and streams progress
window.startRecordingCalibration = async function () {
  const modal = await showModal("calibration-modal");
  const rawLog = document.getElementById("calibration-log");
  const message = document.getElementById("calibration-message");
  const progress = document.getElementById("calibration-progress");
  const results = document.getElementById("calibration-results");
  const endBtn = document.getElementById("end-calibration-game");

  // Use global threshold constant

  // reset UI
  if (rawLog) rawLog.textContent = "";
  if (message) message.textContent = "Keep going";
  if (progress) progress.value = 0;
  if (results) results.style.display = "none";

  // Ensure header, paragraph and end button are visible for a new recording
  try {
    const modalHeader = modal.querySelector("header");
    const modalPara = modal.querySelector("article > p");
    if (modalHeader) modalHeader.style.display = "";
    if (modalPara) modalPara.style.display = "";
    if (endBtn) endBtn.style.display = "";
    if (message) message.style.display = "";
    if (progress) progress.style.display = "";
    if (rawLog) rawLog.style.display = "none"; // keep raw log hidden by default
  } catch (e) {}

  // We'll need to allow the user to manually end the calibration. Keep a flag and a reader reference.
  let reader = null;
  let stopRequested = false;

  // wire end button to stop the stream and show results
  if (endBtn) {
    endBtn.onclick = async () => {
      stopRequested = true;
      // close the stream by canceling reader if active
      try {
        if (reader) await reader.cancel();
      } catch (e) {
        // ignore
      }
      // Request final scores form from server (or show whatever we've received so far)
      // For now we'll try to fetch a final payload from the server via a separate endpoint if available
      // Fallback: show the results form with empty payload
      await buildScoresForm([]);
      // hide the recording UI parts since recording is finished
      if (message) message.style.display = "none";
      if (progress) progress.style.display = "none";
      if (rawLog) rawLog.style.display = "none";
      if (results) results.style.display = "block";
      // refresh recorded games count after user ends
      refreshRecordedGamesCount();
    };
  }

  try {
    const resp = await window.smartFetch(
      "/api/em/record_calibration_game",
      null,
      true,
    );
    if (!resp.ok) {
      alert("Failed to start calibration recording");
      return;
    }

    reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let done = false;
    while (!done && !stopRequested) {
      const { value, done: d } = await reader.read();
      done = d;
      if (value) {
        const chunk = decoder.decode(value, { stream: true });
        // keep raw JSON in hidden log for debugging
        if (rawLog) rawLog.textContent += chunk;

        // Handle concatenated JSON objects like: {"progress":10}{"progress":20}
        let msgs = chunk.split("}{");
        for (let i = 0; i < msgs.length; i++) {
          if (i !== 0) msgs[i] = "{" + msgs[i];
          if (i !== msgs.length - 1) msgs[i] = msgs[i] + "}";
        }

        for (const s of msgs) {
          const line = s.trim();
          if (!line) continue;
          try {
            const msg = JSON.parse(line);
            // support both 'progress' and 'percent' keys
            const pct =
              msg.percent != null
                ? msg.percent
                : msg.progress != null
                ? msg.progress
                : null;
            if (pct != null && progress) progress.value = pct;
            // update static message based on threshold
            if (pct != null && message) {
              if (pct >= CALIBRATION_MESSAGE_THRESHOLD) {
                message.textContent = "Allow your ball to drain";
              } else {
                message.textContent = "Keep going";
              }
            }
            if (msg.log && rawLog) rawLog.textContent += "\n" + msg.log;
            if (msg.complete) {
              await buildScoresForm(msg.payload || []);
              // hide the recording UI parts since recording is finished
              if (message) message.style.display = "none";
              if (progress) progress.style.display = "none";
              if (rawLog) rawLog.style.display = "none";
              if (results) results.style.display = "block";
              // refresh recorded games count after a game has been recorded
              refreshRecordedGamesCount();
            }
          } catch (e) {
            // not json, ignore
          }
        }
      }
    }
  } catch (e) {
    if (!stopRequested) {
      console.error("Calibration recording failed:", e);
      alert("Calibration recording failed.");
    }
  }
};

async function buildScoresForm(payloadScores) {
  // Try to load server-side config if available; otherwise fall back to inputs
  let totalPlayers =
    parseInt(document.getElementById("total-players").value, 10) || 1;
  let reelsPerPlayer =
    parseInt(document.getElementById("score-reels").value, 10) || 1;
  let dummyReels =
    parseInt(document.getElementById("dummy-reels").value, 10) || 0;

  try {
    const resp = await window.smartFetch("/api/em/get_config", null, false);
    if (resp && resp.ok) {
      const cfg = await resp.json();
      if (cfg.players != null)
        totalPlayers = Number(cfg.players) || totalPlayers;
      if (cfg.reels_per_player != null)
        reelsPerPlayer = Number(cfg.reels_per_player) || reelsPerPlayer;
      if (cfg.dummy_reels != null)
        dummyReels = Number(cfg.dummy_reels) || dummyReels;
    }
  } catch (e) {
    // ignore — use existing DOM values
  }

  const form = document.getElementById("calibration-scores-form");
  form.innerHTML = "";

  // Show instruction under the heading
  const instr = document.getElementById("calibration-instructions");
  if (instr) {
    instr.textContent = `Enter full scores for each player. Include dummy reel zeros where appropriate (dummy reels: ${dummyReels}).`;
    instr.style.display = "block";
  }

  // Prefill inputs with zeros equal to reelsPerPlayer + dummyReels
  const prefillCount = reelsPerPlayer + dummyReels;

  for (let p = 0; p < totalPlayers; p++) {
    const playerDiv = document.createElement("div");
    playerDiv.style.marginBottom = "0.5rem";

    // Only create a single label + input per player (remove duplicate title element)
    const label = document.createElement("label");
    label.textContent = `Player ${p + 1}: `;
    const input = document.createElement("input");
    input.type = "text";
    input.placeholder = `comma-separated reel values (e.g. 10,0,0) or concatenated digits for zeros (e.g. 000)`;

    // If payloadScores was provided and contains this player's values, use them; otherwise prefill zeros
    const existingVals =
      (payloadScores && payloadScores[p] && payloadScores[p].slice()) || [];
    if (existingVals.length) {
      input.value = existingVals.join(",");
    } else {
      // Prefill as undelimited zeros (e.g. "000") per UX request
      input.value = new Array(prefillCount).fill(0).join("");
    }

    input.style.width = "18rem";
    input.name = `player-${p}-reel-values`;
    label.appendChild(input);
    playerDiv.appendChild(label);

    form.appendChild(playerDiv);
  }

  // hide pre-recording UI so the modal effectively becomes the score-entry modal
  try {
    const modal = document.getElementById("calibration-modal");
    const modalHeader = modal.querySelector("header");
    const modalPara = modal.querySelector("article > p");
    const endBtn = document.getElementById("end-calibration-game");
    if (modalHeader) modalHeader.style.display = "none";
    if (modalPara) modalPara.style.display = "none";
    if (endBtn) endBtn.style.display = "none";
    // also hide progress and message elements
    const message = document.getElementById("calibration-message");
    const progress = document.getElementById("calibration-progress");
    const rawLog = document.getElementById("calibration-log");
    if (message) message.style.display = "none";
    if (progress) progress.style.display = "none";
    if (rawLog) rawLog.style.display = "none";
  } catch (e) {}

  const saveBtn = document.getElementById("save-calibration-scores");
  if (saveBtn) {
    saveBtn.onclick = async (e) => {
      e.preventDefault();
      await saveCalibrationScores();
    };
  }
}

async function saveCalibrationScores() {
  // Prefer server-provided config (players/reels/dummy) if available
  let totalPlayers =
    parseInt(document.getElementById("total-players").value, 10) || 1;
  let reelsPerPlayer =
    parseInt(document.getElementById("score-reels").value, 10) || 1;
  let dummyReels =
    parseInt(document.getElementById("dummy-reels").value, 10) || 0;
  try {
    const resp = await window.smartFetch("/api/em/get_config", null, false);
    if (resp && resp.ok) {
      const cfg = await resp.json();
      if (cfg.players != null)
        totalPlayers = Number(cfg.players) || totalPlayers;
      if (cfg.reels_per_player != null)
        reelsPerPlayer = Number(cfg.reels_per_player) || reelsPerPlayer;
      if (cfg.dummy_reels != null)
        dummyReels = Number(cfg.dummy_reels) || dummyReels;
    }
  } catch (e) {
    // ignore and use DOM values
  }

  const scores = [];
  for (let p = 0; p < totalPlayers; p++) {
    const el = document.querySelector(`input[name="player-${p}-reel-values"]`);
    const raw = el ? el.value.trim() : "";
    let vals = [];
    if (raw.length > 0) {
      // Support multiple input styles:
      // - comma-separated: "10,0,0"
      // - space-separated: "10 0 0"
      // - undelimited digits (useful for zeros prefills): "000" -> [0,0,0]
      if (raw.indexOf(",") !== -1) {
        vals = raw.split(",").map((s) => parseInt(s.trim(), 10) || 0);
      } else if (/\s/.test(raw)) {
        vals = raw.split(/\s+/).map((s) => parseInt(s.trim(), 10) || 0);
      } else if (/^\d+$/.test(raw) && raw.length >= 1) {
        // If the user entered a pure digit string and its length equals the
        // expected number of reels (including dummy), treat each character
        // as a separate digit value (e.g. "000" -> [0,0,0]). Otherwise
        // interpret as a single numeric value.
        if (raw.length === reelsPerPlayer + dummyReels) {
          vals = raw.split("").map((c) => parseInt(c, 10) || 0);
        } else {
          const n = parseInt(raw, 10);
          if (!isNaN(n)) vals = [n];
        }
      } else {
        // fallback: try comma split anyway
        vals = raw.split(",").map((s) => parseInt(s.trim(), 10) || 0);
      }
    }
    // Ensure we have reelsPerPlayer values; if fewer, pad with zeros; if more, truncate
    const playerScores = [];
    for (let i = 0; i < reelsPerPlayer; i++) {
      playerScores.push(i < vals.length ? vals[i] : 0);
    }
    // append dummy reel zeros
    for (let d = 0; d < dummyReels; d++) playerScores.push(0);
    scores.push(playerScores);
  }

  try {
    const resp = await window.smartFetch(
      "/api/em/set_calibration_scores",
      { scores: scores },
      true,
    );
    if (!resp.ok) throw new Error("save failed");
    document.getElementById("calibration-modal").close();
    // refresh recorded games count after saving
    refreshRecordedGamesCount();
  } catch (e) {
    console.error("Failed to save calibration scores", e);
    alert("Failed to save calibration scores");
  }
}

window.startLearningProcess = async function () {
  // Show modal and stream progress
  const modal = await showModal("learning-modal");
  const log = document.getElementById("learning-log");
  const progress = document.getElementById("learning-progress");
  if (log) log.textContent = "";
  if (progress) progress.value = 0;

  try {
    const resp = await window.smartFetch(
      "/api/em/start_learning_process",
      null,
      true,
    );
    if (!resp.ok) throw new Error("learn start failed");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let done = false;
    while (!done) {
      const { value, done: d } = await reader.read();
      done = d;
      if (value) {
        const chunk = decoder.decode(value, { stream: true });
        if (log) log.textContent += chunk;
        // handle concatenated JSON objects
        let msgs = chunk.split("}{");
        for (let i = 0; i < msgs.length; i++) {
          if (i !== 0) msgs[i] = "{" + msgs[i];
          if (i !== msgs.length - 1) msgs[i] = msgs[i] + "}";
        }
        for (const s of msgs) {
          const line = s.trim();
          if (!line) continue;
          try {
            const obj = JSON.parse(line);
            const pct =
              obj.percent != null
                ? obj.percent
                : obj.progress != null
                ? obj.progress
                : null;
            if (pct != null && progress) progress.value = pct;
          } catch (e) {
            // ignore
          }
        }
      }
    }
    // close modal when done
    if (modal) modal.close();
    refreshRecordedGamesCount();
  } catch (e) {
    console.error("Failed to start learning process", e);
    alert("Failed to start learning process");
    try {
      if (modal) modal.close();
    } catch (err) {}
  }
};

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
// populate recorded games status on load
refreshRecordedGamesCount();

// wire save button
const saveGameConfigBtn = document.getElementById("save-game-config");
if (saveGameConfigBtn) {
  saveGameConfigBtn.style.display = "none";
  saveGameConfigBtn.addEventListener("click", async (e) => {
    e.preventDefault();
    await saveGameConfig();
  });
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

async function applyUpdate(url) {
  req_data = { url: url };
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
  await confirmAction("update with file at " + url, async () => {
    await window.applyUpdate(url);
  });
};
