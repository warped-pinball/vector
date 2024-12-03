let isSettingsChanged = false;

function downloadFile(fileType) {
    alert(`Downloading ${fileType}...`);
    // Replace with actual download functionality
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

function resetLeaderboard() {
    alert('Leaderboard reset!');
    // Add actual reset logic here
}

function resetTournamentBoard() {
    alert('Tournament board reset!');
    // Add actual reset logic here
}

function rebootGame() {
    alert('Game rebooted!');
    // Add actual reboot logic here
}

function resetGameMemory() {
    alert('Game memory reset!');
    // Add actual reset logic here
}

function settingsChanged() {
    isSettingsChanged = true;
    const saveButton = document.getElementById('save-button');
    saveButton.style.display = 'block';
}

function saveSettings() {
    alert('Settings saved!');
    isSettingsChanged = false;
    const saveButton = document.getElementById('save-button');
    saveButton.style.display = 'none';
    // Add actual save logic here
}
