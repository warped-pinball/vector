// 
// Generic / Utility functions
// 

async function confirm_auth_get(url, purpose) {
  confirmAction(purpose, async () => {
    const response = await window.smartFetch(url, null, true);
    if (response.status !== 200 && response.status !== 401) { // 401 already alerted the user that their password was wrong
      console.error(`Failed to ${purpose}:`, response.status);
      alert(`Failed to ${purpose}.`);
    }
  });
}

function confirmAction(message, callback) {
  const modal = document.getElementById('confirm-modal');
  const modalMessage = document.getElementById('modal-message');
  const confirmButton = document.getElementById('modal-confirm-button');

  modalMessage.textContent = `Are you sure you want to ${message}?`;

  confirmButton.onclick = () => {
    callback();
    closeModal();
  };

  modal.showModal();
}

function closeModal() {
  const modal = document.getElementById('confirm-modal');
  modal.close();
}


// 
// Settings
// 

// Tournament Mode
async function tournamentModeToggle() {
  const tournamentModeCheckbox = document.querySelector('input[name="tournament-mode"]');

  // disable the checkbox until we have the current setting
  tournamentModeCheckbox.disabled = true;

  const response = await window.smartFetch('/api/settings/tournament_mode', null, false);
  const data = await response.json();

  tournamentModeCheckbox.checked = data['tournament_mode'];
  tournamentModeCheckbox.disabled = false;

  // add event listener to update the setting when the checkbox is changed
  tournamentModeCheckbox.addEventListener('change', async () => {
    const data = { 'tournament_mode': tournamentModeCheckbox.checked ? 1 : 0 };
    await window.smartFetch('/api/settings/tournament_mode', data, true);
  });
}

// score Claim methods
async function getScoreClaimMethods() {
  const onMachineCheckbox = document.querySelector('input[name="on-machine"]');

  // disable the checkbox until we have the current setting
  onMachineCheckbox.disabled = true;

  const response = await window.smartFetch('/api/settings/score_claim_methods', null, false);
  const data = await response.json();

  onMachineCheckbox.checked = data['on-machine'];
  onMachineCheckbox.disabled = false;

  // add event listener to update the setting when the checkbox is changed
  onMachineCheckbox.addEventListener('change', async () => {
    const data = { 'on-machine': onMachineCheckbox.checked ? 1 : 0 };
    await window.smartFetch('/api/settings/score_claim_methods', data, true);
  });
}

tournamentModeToggle();
getScoreClaimMethods();

// 
// Actions
// 

// Download Logs
window.downloadLogs = async function () {
  console.log("Downloading logs...");

  // Perform the fetch (no auth needed if your endpoint doesn't require it)
  const response = await window.smartFetch('/api/logs', null, false);

  if (!response.ok) {
    console.error("Failed to download logs:", response.status, response.statusText);
    alert("Failed to download logs.");
    return;
  }

  // Get the response as a blob
  const blob = await response.blob();

  // Generate a filename similar to how you do CSVs (with game name, date, etc.)
  let filename = document.getElementById('game_name').innerText;
  filename += '_log_';
  filename += new Date().toISOString().split('T')[0];
  filename += '.txt';

  // Replace spaces with underscores
  filename = filename.replace(/ /g, '_');

  // Create a temporary link to trigger the download
  const url = window.URL.createObjectURL(blob);
  const element = document.createElement('a');
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
  const response = await window.smartFetch('/api/memory-snapshot', null, false);

  if (!response.ok) {
    console.error("Failed to fetch memory snapshot:", response.status, response.statusText);
    alert("Failed to download memory snapshot.");
    return;
  }

  // Get the response as text
  const content = await response.text();

  // Generate a filename similar to how you do CSVs
  let filename = document.getElementById('game_name').innerText;
  filename += '_memory_';
  filename += new Date().toISOString().split('T')[0];
  filename += '.txt';

  // Replace spaces with underscores
  filename = filename.replace(/ /g, '_');

  // Create a temporary link to trigger the download
  const element = document.createElement('a');
  element.href = 'data:text/plain;charset=utf-8,' + encodeURIComponent(content);
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

  const response = await window.smartFetch('/api/export/scores', null, false);

  if (!response.ok) {
    console.error("Failed to download scores:", response.status, response.statusText);
    alert("Failed to download scores.");
    return;
  }

  // Get the response
  const data = await response.json();

  // Generate a filename similar to how you do CSVs (with game name, date, etc.)
  let filename = document.getElementById('game_name').innerText;
  filename += '_scores_';
  filename += new Date().toISOString().split('T')[0];
  filename += '.json';

  // Replace spaces with underscores
  filename = filename.replace(/ /g, '_');

  // Create a temporary link to trigger the download
  const element = document.createElement('a');
  element.href = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(data));
  element.download = filename;
  document.body.appendChild(element);
  element.click();

  // Clean up
  document.body.removeChild(element);

  console.log("Scores download initiated.");
}










// 
// Updates
// 

// confirm compatibility with the update
async function updateIsCompatible(updateData) {
  const compatibility_data = {
    hardware: updateData.hardware,
    micropython_version: updateData.micropython_version,
    software: updateData.software,
    version: updateData.version
  };
  const response = await window.smartFetch("/api/validate_update", compatibility_data, true);
  if (response.status !== 200) {
    console.error("Failed to validate update compatibility:", response.status);
    return false;
  }
  return true;
}

// Filter list of files to only include changed files
async function generateFileIndex(updateData) {
  const chunk_size = updateData.chunk_size;
  const server_index = await window.smartFetch("/api/file/index", { chunk_size }, true);

  if (server_index.status !== 200) {
    console.error("Failed to get server file index:", server_index.status);
    alert("Failed to get server file index.");
    return;
  }

  const serverFileIndex = server_index.data;

  // filter out any files in updateData.files where the checksum matches the server checksum
  const changedFiles = updateData.files.filter(file => {
    const serverFile = serverFileIndex[file.path][file.part];
    return !serverFile || serverFile.checksum !== file.checksum;
  });

  return changedFiles;
}


// Upload only changed files
async function uploadFiles(files) {
  for (const file of files) {
    console.log(`Uploading file ${file.path}, part ${file.part} of ${file.parts}...`);
    const response = await window.smartFetch("/api/upload_file", file, true);
    if (response.status !== 200) {
      //TODO retry the upload?
      //TODO restart the update process? we don't know if this file is corrupted now
      //TODO send over checksums in the hopes that the server can walk back the changes so we can try again
      alert(`Failed to upload file ${file.path}, part ${file.part} of ${file.parts}.`);
    }
  }
}

// Handle the update process
window.applyUpdate = async function (file) {
  try {
    const fileText = await file.text();
    const updateData = JSON.parse(fileText);

    // Step 0: Validate the update file
    // TODO confirm the upate format is one this code is compatible with
    // TODO confirm that all files have required fields
    // TODO confirm that all parts of all files are present
    // TODO confirm the checksums


    // Step 1: Confirm update compatibility
    if (!await updateIsCompatible(updateData)) {
      alert("This file does not appear to be a valid update.", response.statusText);
      return;
    }

    // Step 2: Generate file index and get server's file state
    const serverFileIndex = await generateFileIndex(updateData, null, true);

    // Step 3: Upload changed files
    await uploadFiles(serverFileIndex);

    // Step 4: Confirm the update
    // TODO check the final full checksum of file system
    alert("Update applied successfully. rebooting...");

    // Step 5: Reboot the device
    await window.smartFetch("/api/reboot", null, true);

  } catch (error) {
    console.error("Error applying update:", error);
    alert(`Failed to apply update:\n${error.message}`);
  }
};

// File input handler
window.handleUpdateUploadChange = async function (event) {
  const fileInput = event.target;

  if (!fileInput.files || fileInput.files.length === 0) {
    return; // No file selected
  }

  const file = fileInput.files[0];

  // Confirm user action
  window.confirmAction(`apply the update in ${file.name}`, async () => {
    // disable the input while processing
    fileInput.disabled = true;
    await window.applyUpdate(file);
    fileInput.disabled = false;
    fileInput.value = ""; // Clear the input after processing
  });
};
