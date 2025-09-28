//
// Generic / Utility functions
//

let systemFeatures = null;

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

  const onMachineRow = document.getElementById("on-machine-row");
  let onMachineToggle = null;
  if (systemFeatures && systemFeatures.supports_on_machine_claims) {
    onMachineToggle = await window.waitForElementById("on-machine-toggle");
    onMachineToggle.checked = data["on-machine"];
    onMachineToggle.disabled = false;
  } else if (onMachineRow) {
    onMachineRow.classList.add("hide");
  }

  const webUIToggle = await window.waitForElementById("web-ui-toggle");
  webUIToggle.checked = data["web-ui"];
  webUIToggle.disabled = false;

  function buildClaimMethodPayload() {
    const payload = {};
    if (systemFeatures && systemFeatures.supports_on_machine_claims && onMachineToggle) {
      payload["on-machine"] = onMachineToggle.checked ? 1 : 0;
    }
    if (!systemFeatures || systemFeatures.supports_web_ui_claims !== false) {
      payload["web-ui"] = webUIToggle.checked ? 1 : 0;
    }
    return payload;
  }

  const toggles = [webUIToggle];
  if (onMachineToggle) {
    toggles.push(onMachineToggle);
  }

  toggles.forEach((toggle) => {
    toggle.addEventListener("change", async () => {
      const payload = buildClaimMethodPayload();
      await window.smartFetch("/api/settings/set_claim_methods", payload, true);
    });
  });
}

async function getShowIP() {
  const response = await window.smartFetch(
    "/api/settings/get_show_ip",
    null,
    false,
  );
  const data = await response.json();

  const showIPToggle = await window.waitForElementById("show-ip-toggle");

  showIPToggle.checked = data["show_ip"];
  showIPToggle.disabled = false;

  // add event listener to update the setting when the checkbox is changed
  showIPToggle.addEventListener("change", async () => {
    const data = { show_ip: showIPToggle.checked ? 1 : 0 };
    await window.smartFetch("/api/settings/set_show_ip", data, true);
  });
}

// Midnight Madness settings
async function getMidnightMadness() {
  const response = await window.smartFetch(
    "/api/time/get_midnight_madness",
    null,
    false,
  );
  const data = await response.json();

  const enableToggle = await window.waitForElementById(
    "midnight-madness-enable-toggle",
  );
  const alwaysToggle = await window.waitForElementById(
    "midnight-madness-always-toggle",
  );
  const nowButton = await window.waitForElementById(
    "midnight-madness-now-button",
  );

  enableToggle.checked = data["enabled"];
  alwaysToggle.checked = data["always"];
  nowButton.disabled = !data["enabled"];

  enableToggle.disabled = false;
  alwaysToggle.disabled = false;

  function addListener(toggle, after) {
    toggle.addEventListener("change", async () => {
      const payload = {
        enabled: enableToggle.checked ? 1 : 0,
        always: alwaysToggle.checked ? 1 : 0,
      };
      await window.smartFetch("/api/time/set_midnight_madness", payload, true);
      if (after) after();
    });
  }

  addListener(enableToggle, () => {
    nowButton.disabled = !enableToggle.checked;
  });
  addListener(alwaysToggle);

  nowButton.addEventListener("click", async () => {
    await window.smartFetch("/api/time/trigger_midnight_madness", null, false);
  });
}

async function initMidnightMadness() {
  const section = await window.waitForElementById("midnight-madness-section");
  const response = await window.smartFetch(
    "/api/time/midnight_madness_available",
    null,
    false,
  );
  const data = await response.json();
  if (!data.available) {
    section.classList.add("hide");
    return;
  }
  section.classList.remove("hide");
  await getMidnightMadness();
}

if (typeof window !== "undefined") {
  const emState = {
    scoreReels: 0,
    pendingCaptureId: null,
    calibrationGames: [],
  };

  async function initAdmin() {
    try {
      systemFeatures = await window.getSystemFeatures();
    } catch (error) {
      console.error("Failed to load system features", error);
      systemFeatures = {};
    }

    tournamentModeToggle();

    if (
      systemFeatures.supports_on_machine_claims === false &&
      systemFeatures.supports_web_ui_claims === false
    ) {
      const scoreClaimSection = document.getElementById("score-claim-section");
      if (scoreClaimSection) {
        scoreClaimSection.classList.add("hide");
      }
    } else {
      getScoreClaimMethods();
    }

    if (systemFeatures.supports_show_ip_on_machine) {
      getShowIP();
    } else {
      const showIpSection = document.getElementById("show-ip-section");
      if (showIpSection) {
        showIpSection.classList.add("hide");
      }
    }

    initMidnightMadness();

    if (systemFeatures.supports_adjustment_profiles) {
      populateAdjustmentProfiles();
    } else {
      const adjustmentsSection = document.getElementById("adjustments-section");
      if (adjustmentsSection) {
        adjustmentsSection.classList.add("hide");
      }
    }

    if (systemFeatures.supports_memory_snapshot === false) {
      const snapshotButton = document.getElementById(
        "download-memory-snapshot-button",
      );
      if (snapshotButton) {
        snapshotButton.classList.add("hide");
      }
    }

    if (systemFeatures.supports_em_calibration) {
      await initEmCalibration();
    } else {
      const emSection = document.getElementById("em-calibration-section");
      if (emSection) {
        emSection.classList.add("hide");
      }
    }
  }

  //
  // Adjustment Profiles
  //

  async function populateAdjustmentProfiles() {
    const response = await window.smartFetch(
      "/api/adjustments/status",
      null,
      false,
    );
    const data = await response.json();

    console.log("Adjustment Profiles: ", data);

    if (data.adjustments_support === false) {
      console.log("Adjustments not supported");
      // add note to the page that adjustments are not supported for this title yet
      document
        .getElementById("adjustments-not-supported")
        .classList.remove("hide");
      return;
    }

    // iterate through list of (name, active, captured) and set the values
    const profiles = data.profiles;
    for (let i = 0; i < profiles.length; i++) {
      console.log("Profile: ", profiles[i]);
      const profileName = document.getElementById(`name-profile-${i}`);
      const profileRestore = document.getElementById(`restore-profile-${i}`);
      const profileCapture = document.getElementById(`capture-profile-${i}`);

      profileRestore.checked = profiles[i][1];
      profileRestore.disabled = !profiles[i][2];

      profileName.disabled = false;
      if (profiles[i][0] != "") {
        profileName.placeholder = profiles[i][0];
        profileName.value = "";
      }

      profileCapture.disabled = false;

      // add event listener to capture button
      profileCapture.addEventListener("click", async () => {
        await captureProfile(i);
      });

      // add event listener to restore button
      profileRestore.addEventListener("click", async () => {
        await restoreProfile(i);
      });

      // add event listener to name input
      profileName.addEventListener("blur", async () => {
        await setProfileName(i);
      });
    }
  }

  async function setProfileName(index) {
    const input = document.getElementById(`name-profile-${index}`);
    const name = input.value;

    // check if name is still the placeholder
    if (name === input.placeholder || name === "") {
      return;
    }

    const data = { index: index, name: name };
    try {
      await window.smartFetch("/api/adjustments/name", data, true);
    } catch (e) {
      input.value = input.placeholder;
    }

    // repopulate the profiles
    populateAdjustmentProfiles();
  }

  // capture profile
  async function captureProfile(index) {
    const data = { index: index };
    const profileName = document.getElementById(
      `name-profile-${index}`,
    ).placeholder;
    // build callback function
    const callback = async () => {
      const response = await window.smartFetch(
        "/api/adjustments/capture",
        data,
        true,
      );
      populateAdjustmentProfiles();
    };
    // confirm action
    await confirmAction(
      'overwrite "' + profileName + '" with the currently active adjustments',
      callback,
    );
  }

  // restore profile
  async function restoreProfile(index) {
    const data = { index: index };
    const profileName = document.getElementById(
      `name-profile-${index}`,
    ).placeholder;

    // build callback function
    const callback = async () => {
      // get the current game status
      const gameStatusResponse = await window.smartFetch(
        "/api/game/status",
        null,
        false,
      );
      const gameStatus = await gameStatusResponse.json();

      // if the game is active we can't restore the profile
      if (gameStatus["GameActive"]) {
        alert(
          "Cannot restore adjustments while a game is in progress, please try again after the game has ended.",
        );
        populateAdjustmentProfiles();
        return;
      }

      const response = await window.smartFetch(
        "/api/adjustments/restore",
        data,
        true,
      );
      populateAdjustmentProfiles();
    };
    // confirm action
    await confirmAction(
      'restore adjustment profile: "' + profileName + '" and reboot the game',
      callback,
      populateAdjustmentProfiles, // if we cancel we need to reset the selected / active profile
    );
  }

  //
  // Electromechanical Calibration
  //

  async function refreshEmCalibration() {
    try {
      const response = await window.smartFetch(
        "/api/em/status",
        null,
        false,
      );
      if (!response.ok) {
        throw new Error(`status ${response.status}`);
      }
      const data = await response.json();

      const defaultReels =
        (systemFeatures && systemFeatures.default_score_reels) || 0;
      emState.scoreReels = data.score_reels || defaultReels;
      emState.calibrationGames = data.calibration_games || [];

      const reelCountElement = document.getElementById("em-score-reel-count");
      if (reelCountElement) {
        reelCountElement.textContent = emState.scoreReels || defaultReels;
      }

      const list = document.getElementById("em-calibration-list");
      const emptyMessage = document.getElementById("em-calibration-empty");
      if (list) {
        list.innerHTML = "";
        if (emState.calibrationGames.length === 0) {
          if (emptyMessage) {
            emptyMessage.classList.remove("hide");
          }
        } else {
          if (emptyMessage) {
            emptyMessage.classList.add("hide");
          }
          emState.calibrationGames.forEach((game, index) => {
            const item = document.createElement("li");
            const scores = Array.isArray(game.scores)
              ? game.scores.join(", ")
              : game.scores || "-";
            let description = `Game ${index + 1}: ${scores}`;
            if (game.saved_at) {
              const savedDate = new Date(game.saved_at * 1000);
              if (!Number.isNaN(savedDate.getTime())) {
                description += ` — Saved ${savedDate.toLocaleString()}`;
              }
            }
            item.textContent = description;
            list.appendChild(item);
          });
        }
      }

      const captureButton = document.getElementById("em-capture-button");
      if (captureButton) {
        const maxGames =
          (systemFeatures && systemFeatures.max_calibration_games) || 4;
        captureButton.disabled =
          emState.calibrationGames.length >= maxGames;
      }

      const learningButton = document.getElementById("em-learning-button");
      if (learningButton) {
        learningButton.disabled = emState.calibrationGames.length === 0;
      }
    } catch (error) {
      console.error("Failed to refresh EM calibration status", error);
    }
  }

  function openEmScoreEntryModal(captureId) {
    const modal = document.getElementById("em-score-entry-modal");
    const container = document.getElementById("em-score-inputs");
    if (!modal || !container) {
      return;
    }

    container.innerHTML = "";
    const reelCount =
      emState.scoreReels ||
      (systemFeatures && systemFeatures.default_score_reels) ||
      0;

    for (let i = 0; i < reelCount; i++) {
      const label = document.createElement("label");
      label.htmlFor = `em-score-input-${i}`;
      label.textContent = `Reel ${i + 1}`;

      const input = document.createElement("input");
      input.type = "number";
      input.min = "0";
      input.step = "1";
      input.id = `em-score-input-${i}`;
      input.name = `reel-${i}`;
      input.required = true;

      container.appendChild(label);
      container.appendChild(input);
    }

    emState.pendingCaptureId = captureId;
    modal.showModal();
  }

  function closeEmScoreEntryModal() {
    const modal = document.getElementById("em-score-entry-modal");
    if (modal && modal.open) {
      modal.close();
    }
    emState.pendingCaptureId = null;
  }

  async function handleEmCapture() {
    const modal = document.getElementById("em-capture-progress-modal");
    const progressBar = document.getElementById("em-capture-progress");
    const statusText = document.getElementById("em-capture-status");
    const closeButton = document.getElementById("em-capture-close-button");

    if (!modal || !progressBar || !statusText || !closeButton) {
      console.warn("EM capture UI is missing expected elements.");
      return;
    }

    progressBar.value = 0;
    statusText.textContent = "Preparing to capture…";
    closeButton.disabled = true;
    modal.showModal();

    function processUpdate(update) {
      if (typeof update.progress === "number") {
        progressBar.value = update.progress;
      }
      if (update.message) {
        statusText.textContent = update.message;
      }
      if (update.status === "awaiting_score") {
        closeButton.disabled = false;
        modal.close();
        openEmScoreEntryModal(update.capture_id);
      }
    }

    try {
      const response = await window.smartFetch(
        "/api/em/calibration/start_capture",
        {},
        true,
      );
      if (!response.ok) {
        throw new Error(`status ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) {
            continue;
          }
          processUpdate(JSON.parse(line));
        }
      }

      if (buffer.trim()) {
        processUpdate(JSON.parse(buffer.trim()));
      }
    } catch (error) {
      console.error("Failed to capture calibration game", error);
      statusText.textContent = `Capture failed: ${error.message || error}`;
      closeButton.disabled = false;
      return;
    }

    closeButton.disabled = false;
  }

  async function submitEmScoreForm(event) {
    event.preventDefault();
    if (!emState.pendingCaptureId) {
      alert("There is no captured game to save yet.");
      return;
    }

    const scores = [];
    const reelCount =
      emState.scoreReels ||
      (systemFeatures && systemFeatures.default_score_reels) ||
      0;

    for (let i = 0; i < reelCount; i++) {
      const input = document.getElementById(`em-score-input-${i}`);
      if (!input) {
        continue;
      }
      const value = parseInt(input.value, 10);
      if (Number.isNaN(value)) {
        alert("Please enter a value for each score reel.");
        return;
      }
      scores.push(value);
    }

    try {
      const response = await window.smartFetch(
        "/api/em/calibration/save_game",
        {
          capture_id: emState.pendingCaptureId,
          scores,
        },
        true,
      );
      if (!response.ok) {
        throw new Error(`status ${response.status}`);
      }

      await response.json();
      closeEmScoreEntryModal();
      await refreshEmCalibration();
    } catch (error) {
      console.error("Failed to save calibration game", error);
      alert("Unable to save calibration game. Please try again.");
    }
  }

  async function initEmCalibration() {
    const section = document.getElementById("em-calibration-section");
    if (!section) {
      return;
    }

    section.classList.remove("hide");

    const captureButton = document.getElementById("em-capture-button");
    const closeButton = document.getElementById("em-capture-close-button");
    const scoreForm = document.getElementById("em-score-entry-form");
    const cancelButton = document.getElementById("em-score-entry-cancel");
    const learningButton = document.getElementById("em-learning-button");
    const learningStatus = document.getElementById("em-learning-status");
    const progressModal = document.getElementById(
      "em-capture-progress-modal",
    );

    if (captureButton) {
      captureButton.addEventListener("click", async () => {
        await handleEmCapture();
      });
    }

    if (closeButton) {
      closeButton.addEventListener("click", () => {
        if (progressModal && progressModal.open) {
          progressModal.close();
        }
      });
    }

    if (scoreForm) {
      scoreForm.addEventListener("submit", submitEmScoreForm);
    }

    if (cancelButton) {
      cancelButton.addEventListener("click", (event) => {
        event.preventDefault();
        closeEmScoreEntryModal();
      });
    }

    if (learningButton) {
      learningButton.addEventListener("click", async () => {
        try {
          const response = await window.smartFetch(
            "/api/em/calibration/start_learning",
            {},
            true,
          );
          if (!response.ok) {
            throw new Error(`status ${response.status}`);
          }
          const result = await response.json();
          if (learningStatus) {
            const timestamp = result.timestamp
              ? new Date(result.timestamp * 1000)
              : null;
            const formatted =
              timestamp && !Number.isNaN(timestamp.getTime())
                ? timestamp.toLocaleString()
                : "just now";
            learningStatus.textContent = `Learning started with ${result.games_available} calibration game(s) (${formatted}).`;
          } else {
            alert("Learning process started.");
          }
        } catch (error) {
          console.error("Failed to start learning process", error);
          alert("Unable to start the learning process. Please try again.");
        }
      });
    }

    await refreshEmCalibration();
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
    const response = await window.smartFetch(
      "/api/memory-snapshot",
      null,
      false,
    );

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
    element.href =
      "data:text/plain;charset=utf-8," + encodeURIComponent(content);
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
      "data:text/json;charset=utf-8," +
      encodeURIComponent(JSON.stringify(data));
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
      const response = await window.smartFetch(
        "/api/update/check",
        null,
        false,
      );
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
          await confirmAction(
            "update to version: " + data["version"],
            callback,
          );
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
    const response = await window.smartFetch(
      "/api/update/apply",
      req_data,
      true,
    );
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

  initAdmin();
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
}
