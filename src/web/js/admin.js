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

async function checkForUpdates() {
	
	// wait 3 seconds before checking for updates
	// this lets us prioritize loading the page and settings
	await new Promise(resolve => setTimeout(resolve, 3000));
	
	const response = await window.smartFetch('/api/update/check', null, false);
	const data = await response.json();
	const updateButton = document.getElementById('update-button');
	
	if (data['current'] === data['reccomended']) {
		
		// TODO when no update allow the user to input their own url to download the update
		
		// no update available	
		updateButton.style.backgroundColor = '#8e8e8e';
		updateButton.style.borderColor = '#8e8e8e';
		updateButton.textContent = 'Up to date';
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
			// TODO confirm action
			req_data = {
				'url':data['releases'][data['reccomended']]['update-url']
			};
			const response = await window.smartFetch('/api/update/apply', req_data, true);
			if (response.status !== 200) {
				console.error('Failed to apply update:', response.status);
				alert('Failed to apply update.');
			}
		});
	}
}

checkForUpdates();
