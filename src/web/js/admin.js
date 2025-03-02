//
// Generic / Utility functions
//

async function confirm_auth_get(url, purpose) {
  confirmAction(purpose, async () => {
    const response = await window.smartFetch(url, null, true);
    if (response.status !== 200 && response.status !== 401) {
      // 401 already alerted the user that their password was wrong
      console.error(`Failed to ${purpose}:`, response.status);
      alert(`Failed to ${purpose}.`);
    }
  });
}

function confirmAction(message, callback, cancelCallback = null) {
  const modal = document.getElementById("confirm-modal");
  const modalMessage = document.getElementById("modal-message");
  const confirmButton = document.getElementById("modal-confirm-button");
  const cancelButton = document.getElementById("modal-cancel-button");

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

  const tournamentModeToggle = document.getElementById(
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

  const onMachineToggle = document.getElementById("on-machine-toggle");
  const webUIToggle = document.getElementById("web-ui-toggle");

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

  const showIPToggle = document.getElementById("show-ip-toggle");

  showIPToggle.checked = data["show_ip"];
  showIPToggle.disabled = false;

  // add event listener to update the setting when the checkbox is changed
  showIPToggle.addEventListener("change", async () => {
    const data = { show_ip: showIPToggle.checked ? 1 : 0 };
    await window.smartFetch("/api/settings/set_show_ip", data, true);
  });
}

tournamentModeToggle();
getScoreClaimMethods();
getShowIP();

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
    const data = await response.json();
    const updateButton = document.getElementById("update-button");

    // get the current version from the page
    const current = document
      .getElementById("version")
      .textContent.split(" ")[1];

    // link to release notes in text
    const releaseNotes = document.getElementById("release-notes");
    try {
      // check that the release notes are available
      if (!data["html_url"] || !data["tag_name"]) {
        throw new Error("No release notes available");
      }
      releaseNotes.href = data["html_url"];
      releaseNotes.textContent = "Release Notes for " + data["tag_name"];
    } catch (e) {
      releaseNotes.classList.add("hide");
    }

    // if the latest is equal to the current version we are up to date
    if (data["tag_name"] === current) {
      updateButton.style.backgroundColor = "#8e8e8e";
      updateButton.style.borderColor = "#8e8e8e";
      updateButton.textContent = "Already up to date";
      updateButton.disabled = true;
    } else if (!data["assets"].find((asset) => asset.name === "update.json")) {
      console.error("No update.json asset found for latest version");
      updateButton.textContent = "Could not get updates";
      updateButton.disabled = true;
    } else {
      // there is an update with an update.json asset

      // update available
      updateButton.disabled = false;
      updateButton.style.backgroundColor = "#e8b85a";
      updateButton.style.borderColor = "#e8b85a";
      updateButton.textContent = `Update to ${data["tag_name"]}`;

      // get the url for the update.json asset and add an event listener to the button
      update_url = data["assets"].find(
        (asset) => asset.name === "update.json",
      ).browser_download_url;

      // define the call back function to apply the update
      const callback = async () => {
        await applyUpdate(update_url);
      };

      updateButton.addEventListener("click", async () => {
        await confirmAction("update to version: " + data["tag_name"], callback);
      });
    }
  } catch (e) {
    console.error("Failed to check for updates:", e);
    const updateButton = document.getElementById("update-button");
    updateButton.textContent = "Could not get updates";
    updateButton.disabled = true;
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
