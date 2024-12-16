let isSettingsChanged = false;

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

async function resetGameMemory() {
    const response = await fetch('/api/memory/reset');
    if (response.status !== 200) {
        console.error('Failed to reset game memory:', response.status);
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