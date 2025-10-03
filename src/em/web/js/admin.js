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
  try {
    const resp = await window.smartFetch("/api/em/config", null, false);
    if (resp.ok) {
      const cfg = await resp.json();
      const name = document.getElementById("game-name");
      const players = document.getElementById("total-players");
      const reels = document.getElementById("score-reels");
      const dummy = document.getElementById("dummy-reels");
      if (name && cfg.name) name.value = cfg.name;
      if (players && cfg.total_players) players.value = cfg.total_players;
      if (reels && cfg.score_reels) reels.value = cfg.score_reels;
      if (dummy && cfg.dummy_reels) dummy.value = cfg.dummy_reels;
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
    });
  });

  // populate from localStorage if available
  try {
    const stored = JSON.parse(localStorage.getItem("game_config") || "null");
    if (stored) {
      document.getElementById("game-name").value = stored.name || "";
      document.getElementById("total-players").value =
        stored.total_players || 1;
      document.getElementById("score-reels").value = stored.score_reels || 1;
      document.getElementById("dummy-reels").value = stored.dummy_reels || 0;
    }
  } catch (e) {}
}

// Start recording a calibration game - opens modal and streams progress
window.startRecordingCalibration = async function () {
  const modal = await showModal("calibration-modal");
  const log = document.getElementById("calibration-log");
  const progress = document.getElementById("calibration-progress");
  const results = document.getElementById("calibration-results");

  // reset UI
  if (log) log.textContent = "";
  if (progress) progress.value = 0;
  if (results) results.style.display = "none";

  try {
    const resp = await window.smartFetch(
      "/api/em/record_calibration_game",
      null,
      false,
    );
    if (!resp.ok) {
      alert("Failed to start calibration recording");
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let done = false;
    while (!done) {
      const { value, done: d } = await reader.read();
      done = d;
      if (value) {
        const chunk = decoder.decode(value, { stream: true });
        if (log) log.textContent += chunk;
        const lines = chunk
          .split(/\r?\n/)
          .map((l) => l.trim())
          .filter(Boolean);
        for (const line of lines) {
          try {
            const msg = JSON.parse(line);
            if (msg.percent && progress) progress.value = msg.percent;
            if (msg.log && log) log.textContent += "\n" + msg.log;
            if (msg.complete) {
              buildScoresForm(msg.payload || []);
              if (results) results.style.display = "block";
            }
          } catch (e) {
            // not json, ignore
          }
        }
        if (log) log.scrollTop = log.scrollHeight;
      }
    }
  } catch (e) {
    console.error("Calibration recording failed:", e);
    alert("Calibration recording failed.");
  }
};

function buildScoresForm(payloadScores) {
  const totalPlayers =
    parseInt(document.getElementById("total-players").value, 10) || 1;
  const reelsPerPlayer =
    parseInt(document.getElementById("score-reels").value, 10) || 1;
  const dummyReels =
    parseInt(document.getElementById("dummy-reels").value, 10) || 0;

  const form = document.getElementById("calibration-scores-form");
  form.innerHTML = "";

  for (let p = 0; p < totalPlayers; p++) {
    const playerDiv = document.createElement("div");
    playerDiv.style.marginBottom = "0.5rem";
    const title = document.createElement("div");
    title.textContent = `Player ${p + 1}`;
    playerDiv.appendChild(title);

    const playerScores = (payloadScores[p] && payloadScores[p].slice()) || [];

    for (let r = 0; r < reelsPerPlayer; r++) {
      const idx = r;
      const label = document.createElement("label");
      label.textContent = `Reel ${r + 1}: `;
      const input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.value = playerScores[idx] != null ? playerScores[idx] : 0;
      input.style.width = "8rem";
      input.name = `player-${p}-reel-${r}`;
      label.appendChild(input);
      playerDiv.appendChild(label);
    }

    if (dummyReels > 0) {
      const dummyDiv = document.createElement("div");
      dummyDiv.textContent = `Dummy reels: ${dummyReels} (will be padded with zeros)`;
      playerDiv.appendChild(dummyDiv);
    }

    form.appendChild(playerDiv);
  }

  const saveBtn = document.getElementById("save-calibration-scores");
  if (saveBtn) {
    saveBtn.onclick = async (e) => {
      e.preventDefault();
      await saveCalibrationScores();
    };
  }
}

async function saveCalibrationScores() {
  const totalPlayers =
    parseInt(document.getElementById("total-players").value, 10) || 1;
  const reelsPerPlayer =
    parseInt(document.getElementById("score-reels").value, 10) || 1;
  const dummyReels =
    parseInt(document.getElementById("dummy-reels").value, 10) || 0;

  const scores = [];
  for (let p = 0; p < totalPlayers; p++) {
    const playerScores = [];
    for (let r = 0; r < reelsPerPlayer; r++) {
      const el = document.querySelector(`input[name="player-${p}-reel-${r}"]`);
      const v = el ? parseInt(el.value, 10) || 0 : 0;
      playerScores.push(v);
    }
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
    alert("Calibration scores saved");
    document.getElementById("calibration-modal").close();
  } catch (e) {
    console.error("Failed to save calibration scores", e);
    alert("Failed to save calibration scores");
  }
}

window.startLearningProcess = async function () {
  try {
    const resp = await window.smartFetch(
      "/api/em/start_learning_process",
      null,
      true,
    );
    if (!resp.ok) throw new Error("learn start failed");
    alert("Learning process started");
  } catch (e) {
    console.error("Failed to start learning process", e);
    alert("Failed to start learning process");
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
      update_url = data["url"];

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
