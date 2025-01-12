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
	const tournamentModeToggle = document.getElementById('tournament-mode-toggle');

	// disable the checkbox until we have the current setting
	tournamentModeToggle.disabled = true;

	const response = await window.smartFetch('/api/settings/tournament_mode', null, false);
	const data = await response.json();

	tournamentModeToggle.checked = data['tournament_mode'];
	tournamentModeToggle.disabled = false;

	// add event listener to update the setting when the checkbox is changed
	tournamentModeToggle.addEventListener('change', async () => {
		const data = { 'tournament_mode': tournamentModeToggle.checked ? 1 : 0 };
		await window.smartFetch('/api/settings/tournament_mode', data, true);
	});
}

// score Claim methods
async function getScoreClaimMethods() {
	const onMachineToggle = document.getElementById('on-machine-toggle');

	// disable the checkbox until we have the current setting
	onMachineToggle.disabled = true;

	const response = await window.smartFetch('/api/settings/score_claim_methods', null, false);
	const data = await response.json();

	onMachineToggle.checked = data['on-machine'];
	onMachineToggle.disabled = false;

	// add event listener to update the setting when the checkbox is changed
	onMachineToggle.addEventListener('change', async () => {
		const data = { 'on-machine': onMachineToggle.checked ? 1 : 0 };
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

async function checkForUpdates() {
	
	// wait 3 seconds before checking for updates
	// this lets us prioritize loading the page and settings
	await new Promise(resolve => setTimeout(resolve, 3000));
	
	const response = await window.smartFetch('/api/update/check', null, false);
	const data = await response.json();
	const updateButton = document.getElementById('update-button');
	
	try {
		if (data['current'] === data['reccomended']) {
						
			// no update available	
			updateButton.style.backgroundColor = '#8e8e8e';
			updateButton.style.borderColor = '#8e8e8e';
			updateButton.textContent = 'Already up to date';
			updateButton.disabled = true;

			// try to link to current release notes data[data['current']]['release-url']
			const releaseNotes = document.getElementById('release-notes');
			try {
				releaseNotes.href = data['releases'][data['current']]['release-url'];
				releaseNotes.textContent = 'Release Notes for ' + data['current'];
			} catch (e) {
				releaseNotes.classList.add('hide');
			}
			
		} else {
			// update available
			updateButton.disabled = false;
			updateButton.style.backgroundColor = '#e8b85a';
			updateButton.style.borderColor = '#e8b85a';
			updateButton.textContent = `Update to ${data['reccomended']}`;

			// link to release notes in text
			const releaseNotes = document.getElementById('release-notes');
			releaseNotes.href = data['releases'][data['reccomended']]['release-url'];
			releaseNotes.textContent = 'Release Notes for ' + data['reccomended'];

			updateButton.addEventListener('click', async () => {
				const url = data['releases'][data['reccomended']]['update-url']
				await confirmAction("update to " + data['reccomended'], applyUpdate(url));
			});
		}
	} catch (e) {
		console.error('Failed to check for updates:', e);
		updateButton.textContent = 'Could not get updates';
		updateButton.disabled = true;
	}
}

async function applyUpdate(url) {
	req_data = { 'url': url };
	const response = await window.smartFetch('/api/update/apply', req_data, true);
	if (!response.ok) {
		throw new Error('Failed to start update');
	}

	const updateModal = document.getElementById('update-progress-modal');
	updateModal.showModal();

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	const progressBar = document.getElementById('update-progress-bar');
	const updateProgressLog = document.getElementById('update-progress-log');

	try {
		while (true) {
			const { value, done } = await reader.read();
			if (done) break;
			let msg = decoder.decode(value, { stream: true });
			
			msg = msg.split('}{');
			for (let i = 0; i < msg.length; i++) {
				if (i !== 0) {
					msg[i] = '{' + msg[i];
				}
				if (i !== msg.length - 1) {
					msg[i] = msg[i] + '}';
				}
			}

			for (let i = 0; i < msg.length; i++) {
				const msg_obj = JSON.parse(msg[i]);
				
				if (msg_obj.log) {
					updateProgressLog.textContent += msg_obj.log + '\n';
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
			updateProgressLog.textContent += 'Connection lost.\n';
			updateProgressLog.textContent += 'Refresh the page and Try again.\n';
			progressBar.value = 0;
			return;
		}
	}

	if (response.status !== 200) {
		updateProgressLog.textContent += 'Failed to apply update.\n';
		updateProgressLog.textContent += 'Status: ' + response.status + '\n';
		updateProgressLog.textContent += 'Status Text: ' + response.statusText + '\n';
	}
}

checkForUpdates();
window.applyUpdate = applyUpdate;

// custom update function
window.customUpdate = async function () {
	// prompt the user for the update url
	const url = prompt('Enter the URL for the update');
	if (url === null) {
		return;
	}
	// confirm url
	await confirmAction("update with file at " + url, async () => {
		await window.applyUpdate(url);
	});
}
