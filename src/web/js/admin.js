// 
// Generic / Utility functions
// 

async function confirm_auth_get(url, purpose) {
    confirmAction(purpose, async () => {
        const response = await window.smartFetch(url, null, true);
        if (response.status !== 200) {
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


getScoreClaimMethods();


// adjustments profiles
// TODO: implement this

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
    window.confirmAction(`apply the update from "${file.name}"`, async () => {
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