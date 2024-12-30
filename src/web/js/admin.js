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
    const response = await window.smartFetch('/api/settings/tournament_mode');
    const data = await response.json();

    const tournamentModeCheckbox = document.querySelector('input[name="tournament-mode"]');
    tournamentModeCheckbox.checked = data['tournament_mode'];

    // add event listener to update the setting when the checkbox is changed
    tournamentModeCheckbox.addEventListener('change', async () => {
        const data = { 'tournament_mode': tournamentModeCheckbox.checked ? 1 : 0 };
        await window.smartFetch('/api/settings/tournament_mode', data, true);
    });
}

// score Claim methods
async function getScoreClaimMethods() {
  const response = await fetch('/api/settings/score_claim_methods');
  const data = await response.json();

  const onMachineCheckbox = document.querySelector('input[name="on-machine"]');
  onMachineCheckbox.checked = data['on-machine'];

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


/**
 * The 'onChange' handler for our file input.
 * This is called directly from the HTML input via onChange="window.handleUpdateUploadChange(event)"
 */
window.handleUpdateUploadChange = async function(event) {
    const fileInput = event.target;
    if (!fileInput.files || fileInput.files.length === 0) {
      // No file selected, user canceled, or error
      return;
    }
  
    const file = fileInput.files[0];
    
    // Confirm we want to apply this update
    window.confirmAction(`apply the update in ${file.name}`, async () => {
      // If the user confirms, run the upload
      await window.uploadUpdateFile(file);
      // Optionally clear the input so the user can select again
      fileInput.value = "";
    });
  };
  
  /**
   * Reads the selected file, parses it as JSON, 
   * then uploads any file definitions in sequence to /api/upload_file.
   */
  window.uploadUpdateFile = async function(file) {
    try {
      const fileText = await file.text();
  
      let updates;
      try {
        updates = JSON.parse(fileText);
      } catch (parseErr) {
        alert("Invalid JSON file.");
        throw parseErr;
      }
  
      // If the JSON might be a single object, make it an array
      if (!Array.isArray(updates)) {
        updates = [updates];
      }
  
      // Loop over each item in 'updates' in order
      for (let i = 0; i < updates.length; i++) {
        const item = updates[i];
        console.log(`Uploading file #${i + 1} of ${updates.length}:`, item.FileType || "Unknown");
  
        // Use your smartFetch with authentication
        const response = await window.smartFetch("/api/upload_file", item, true);
  
        if (!response.ok) {
          // Server returned e.g. 500 or other error
          const errorText = await response.text();
          console.error("Upload error:", errorText);
          alert(`Upload of file #${i + 1} failed.\n${errorText}`);
          return; // Stop processing further
        }
  
        // Parse JSON
        const resultData = await response.json();
        if (resultData.status === "error") {
          // The server returned 200 but with an "error" status in the JSON
          console.error("Upload error (JSON response):", resultData);
          alert(`Upload of file #${i + 1} failed.\n${resultData.message || "Unknown error"}`);
          return; // Stop further
        }
  
        console.log(`File #${i + 1} uploaded successfully:`, resultData);
      }
  
      // If we made it here, all files in the array were uploaded successfully
      alert("All updates applied successfully!");
  
    } catch (err) {
      console.error("Exception during update upload:", err);
      alert("Error applying updates:\n" + err.message);
    }
  };


//
// Download Logs
//
window.downloadLogs = async function() {
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

//
// Download Memory Snapshot
//
window.downloadMemorySnapshot = async function() {
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

// 
// Download Scores
// 
window.downloadScores = async function() {
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