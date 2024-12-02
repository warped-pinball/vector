function downloadFile(fileType) {
    alert(`Downloading ${fileType}...`);
    // Replace with actual download functionality
}

function confirmAction(action) {
    if (confirm(`Are you sure you want to ${action}?`)) {
        alert(`${action} confirmed.`);
        // Replace with actual action functionality
    } else {
        alert(`${action} canceled.`);
    }
}

window.confirmAction = confirmAction;