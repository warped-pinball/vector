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

  const onMachineToggle = await window.waitForElementById("on-machine-toggle");
  const webUIToggle = await window.waitForElementById("web-ui-toggle");

  onMachineToggle.checked = data["on-machine"];
  onMachineToggle.disabled = false;

  webUIToggle.checked = data["web-ui"];
  webUIToggle.disabled = false;

  // Helper function to add event listener to claim method toggle
  function addClaimMethodToggleListener(toggle) {
    toggle.addEventListener("change", async () => {
      const data = {
        "on-machine": onMachineToggle.checked ? 1 : 0,
        "web-ui": webUIToggle.checked ? 1 : 0,
      };
      await window.smartFetch("/api/settings/set_claim_methods", data, true);
    });
  }

  // Apply listener to both toggles
  addClaimMethodToggleListener(onMachineToggle);
  addClaimMethodToggleListener(webUIToggle);
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
  tournamentModeToggle();
  getScoreClaimMethods();
  getShowIP();
  initMidnightMadness();

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

  populateAdjustmentProfiles();

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

  // Import Scores
  window.clickedImportScores = async function () {
    var fileInput = document.querySelector("#input_scores");
    fileInput.onchange = (e) => {
      var file = e.target.files[0];
      file.filename;
      window.importScores(file);
    };
    fileInput.click();
  };

  window.importScores = async function (file) {
    if (file.name == "" || file.size == 0) {
      return;
    }
    if (file.type != "application/json") {
      alert("Not a JSON file!");
    }
    console.log("Importing scores...");
    var fileInput = document.querySelector("#input_scores");
    var fileBtn = document.querySelector("#input_scores_btn");
    if (file) {
      const previousText = fileBtn.innerHTML;
      try {
        const fileContent = await file.text(); // Read file as text
        const data = JSON.parse(fileContent); // Parse the text into JSON
        var response_json = null;
        fileBtn.disabled = true;
        fileBtn.innerHTML = "Importing...";
        const response = await window.smartFetch(
          "/api/import/scores",
          data,
          true,
        );
        response_json = await response.json();
      } catch (e) {
        console.error(e);
        return;
      }
      fileInput.value = "";
      fileBtn.innerHTML = previousText;
      fileBtn.disabled = false;
      if (response_json != null && response_json["success"]) {
        //TODO: would be nice to use the modals here...
        alert("Imported!");
      } else {
        if (response.status != 401) {
          //Show an error only if auth didn't fail.
          alert("Error Importing!");
        }
      }
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
      const accordion = document.getElementById("release-notes-btn");
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
          accordion.removeAttribute("disabled");
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

  async function applyUpdate(url, skip_signature_check = false) {
    const req_data = { url: url, skip_signature_check: skip_signature_check };
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
      "Do you trust the source of this update and want to apply the update file at the url:" +
        url,
      async () => {
        await window.applyUpdate(url, true);
      },
    );
  };
}

//
// Origin
//

let originButton;

async function getOriginStatus() {
  const response = await window.smartFetch("/api/origin/status", null, false);
  if (!response.ok) {
    throw new Error("status " + response.status);
  }
  return response.json();
}

function applyOriginStatus(status) {
  originButton.classList.remove("gold-pulse");
  originButton.disabled = false;

  if (status.linked && status.is_claimed && status.username) {
    // Machine is linked and claimed by a user
    originButton.textContent = `Connected to user: ${status.username}`;
    originButton.disabled = true;
    originButton.onclick = null;
  } else if (status.linked) {
    originButton.textContent = "Connected to Warp Pinball Network";
    originButton.onclick = () => {
      if (status.claim_url)
        window.open(status.claim_url, "_blank", "noopener,noreferrer");
    };
  } else if (status.claim_url) {
    originButton.classList.add("gold-pulse");
    originButton.textContent = "Claim this machine";
    originButton.onclick = () =>
      window.open(status.claim_url, "_blank", "noopener,noreferrer");
  } else {
    originButton.classList.add("gold-pulse");
    originButton.textContent = "Connect to Warped Pinball Network";
    originButton.onclick = enableOrigin;
  }
}

async function enableOrigin() {
  originButton.classList.remove("gold-pulse");
  originButton.disabled = true;
  originButton.textContent = "Establishing Connection...";
  try {
    const response = await window.smartFetch("/api/origin/enable", null, true);
    if (!response.ok) {
      throw new Error("status " + response.status);
    }
    const data = await response.json();
    applyOriginStatus(data);
  } catch (e) {
    console.error("Failed to enable origin", e);
    alert("Failed to enable Origin");
    originButton.classList.add("gold-pulse");
    originButton.disabled = false;
    originButton.textContent = "Connect to Warped Pinball Network";
    originButton.onclick = enableOrigin;
  }
}

async function initOriginIntegration() {
  originButton = await window.waitForElementById("link-origin-button");
  originButton.disabled = true;
  try {
    const status = await getOriginStatus();
    applyOriginStatus(status);
  } catch (e) {
    console.error("Failed to get origin status", e);
    originButton.disabled = false;
    originButton.textContent = "Retry";
    originButton.onclick = initOriginIntegration;
  }
}

initOriginIntegration();
