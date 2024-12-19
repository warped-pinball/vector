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
    const data = JSON.stringify({ 'on-machine': onMachineCheckbox.checked });
    await window.smartFetch('/api/settings/score_claim_methods', data, true);
  });
}


getScoreClaimMethods();


// adjustments profiles
// TODO: implement this

// 
// Actions
// 
