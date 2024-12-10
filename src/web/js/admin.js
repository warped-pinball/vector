let isSettingsChanged = false;

const fileTypeEndpoints = {
  'leaderboard': {
    endpoint: '/download_leaders',
    defaultFileName: 'Leaders.json',
    contentType: 'application/json;charset=utf-8'
  },
  'player-names': {
    endpoint: '/download_names',
    defaultFileName: 'Names.json',
    contentType: 'application/json;charset=utf-8'
  },
  'tournament-scores': {
    endpoint: '/download_tournament',
    defaultFileName: 'Tournament.json',
    contentType: 'application/json;charset=utf-8'
  },
  'memory-values': {
    endpoint: '/download_memory',
    defaultFileName: 'MemoryImage.txt',
    contentType: 'text/plain;charset=utf-8'
  },
  'logs': {
    endpoint: '/download_log',
    defaultFileName: 'Log.txt',
    contentType: 'text/plain;charset=utf-8'
  }
};

async function downloadFile(fileType) {
  const fileInfo = fileTypeEndpoints[fileType];
  if (!fileInfo) {
    console.error(`Unknown file type: ${fileType}`);
    return;
  }

  const { endpoint, defaultFileName } = fileInfo;
  try {
    const response = await fetch(endpoint);

    if (!response.ok) {
      console.error(`Failed to download ${fileType}`);
      alert(`Failed to download ${fileType}`);
      return;
    }

    const blob = await response.blob();
    const fileName = prompt("Enter the file name for the download:", defaultFileName) || defaultFileName;
    const url = window.URL.createObjectURL(blob);
    const element = document.createElement('a');
    element.setAttribute('href', url);
    element.setAttribute('download', fileName);

    document.body.appendChild(element);
    element.click();
    document.body.removeChild(element);

    window.URL.revokeObjectURL(url); // Clean up the object URL
  } catch (error) {
    console.error(`Failed to download ${fileType}:`, error);
    alert(`Failed to download ${fileType}.`);
  }
}

function confirmAction(message, callback) {
  const modal = document.getElementById('modal');
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
  const modal = document.getElementById('modal');
  modal.close();
}

async function resetLeaderboard() {
  try {
    await fetch('/api/leaderbaord/reset');
    alert('Leaderboard reset!');
  } catch (error) {
    console.error('Failed to reset leaderboard:', error);
    alert('Failed to reset leaderboard.');
  }
}

async function resetTournamentBoard() {
  try {
    await fetch('/api/tournament/reset');
    alert('Tournament board reset!');
  } catch (error) {
    console.error('Failed to reset tournament board:', error);
    alert('Failed to reset tournament board.');
  }
}

async function rebootGame() {
  try {
    await fetch('/api/game/reboot');
    alert('Game rebooted!');
  } catch (error) {
    console.error('Failed to reboot game:', error);
    alert('Failed to reboot game.');
  }
}

async function resetGameMemory() {
  try {
    await fetch('/api/memory/reset');
    alert('Game memory reset!');
  } catch (error) {
    console.error('Failed to reset game memory:', error);
    alert('Failed to reset game memory.');
  }
}

function settingsChanged() {
  isSettingsChanged = true;
  const saveButton = document.getElementById('save-button');
  saveButton.style.display = 'block';
}

async function saveSettings() {
  const saveButton = document.getElementById('save-button');
  saveButton.disabled = true;

  const onMachineCheckbox = document.querySelector('input[name="claim-on-machine"]');
  const enableScoreCapture = onMachineCheckbox.checked;

  const datePicker = document.getElementById('date-picker');
  const newDate = datePicker.value;

  try {
    // Update enableScoreCapture
    await fetch('/api/settings/score_capture_methods', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ "on-machine": enableScoreCapture })
    });

    // Update date
    await fetch('/api/date_time', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // list of 6 numbers, [year, month, day, hour, minute, second]
      body: JSON.stringify(newDate.split('-').map(Number))
    });

    alert('Settings saved!');
    isSettingsChanged = false;
    saveButton.style.display = 'none';
  } catch (error) {
    console.error('Failed to save settings:', error);
    alert('Failed to save settings.');
  } finally {
    saveButton.disabled = false;
  }
}

async function uploadUpdateFile() {
  const fileInput = document.getElementById('update-upload');
  const file = fileInput.files[0];

  if (!file) {
    alert('Please select a file.');
    return;
  }

  const uploadButton = document.querySelector('button[onclick*="update-upload"]');
  uploadButton.disabled = true;
  uploadButton.textContent = 'Uploading...';

  try {
    const fileContent = await file.text();
    const data = JSON.parse(fileContent);

    if (Array.isArray(data)) {
      for (const item of data) {
        await sendDictionary(item);
      }
      alert('All dictionaries uploaded successfully');

      const resultResponse = await fetch('/upload_results');//TODO update this route when it's written
      const resultText = await resultResponse.text();
      alert(resultText);
    } else {
      alert('File does not contain a valid JSON array.');
    }
  } catch (error) {
    console.error('Failed to process file:', error);
    alert('File processing failed');
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = 'Upload Update File';
    fileInput.value = '';
  }
}

async function sendDictionary(dict) {
  const formData = new FormData();
  formData.append('dictionary', JSON.stringify(dict));

  try {
    const response = await fetch('/upload_file', { //TODO update this route when it's written
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      throw new Error('Network response was not ok');
    }
  } catch (error) {
    console.error('Failed to upload dictionary:', error);
    alert('Dictionary upload failed');
  }
}
