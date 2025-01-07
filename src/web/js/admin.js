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
async function update_file_is_valid(updateData) {
	updateProgress("Validating compatible update file format");
	if (!updateData.update_file_format) {
		console.error("Missing update_file_format in update:", update);
		return false;
	} else if (updateData.update_file_format !== "1.0") {
		console.error("Invalid update_file_format in update:", updateData.update_file_format);
		return false;
	}

	// confirm that all files have required fields
	updateProgress("Validating update file structure");
	for (const file of updateData.files) {
		if (!file.path || !file.checksum || !file.data || !file.final_bytes) {
			console.error("Invalid file in update:", file);
			return false;
		}
	}
	
	// ensure all updateData.files.path start with '/'
	updateProgress("Validating file paths");
	for (const file of updateData.files) {
		if (file.path[0] !== '/') {
			file.path = '/' + file.path;
		}
	}
	
	// confirm that all parts of all files are present
	updateProgress("Validating complete file parts");
	const parts = {};
	for (const file of updateData.files) {
		const num_parts = Math.ceil(file.final_bytes / updateData.chunk_size);
		if (num_parts > 1){
			if (!parts[file.path]) {
				// make a list the length of the number of parts
				parts[file.path] = new Array(num_parts);
			}
			parts[file.path][file.part-1] = { checksum: file.checksum, data: file.data };
		}
	}
	for (const path in parts) {
		const fileParts = parts[path];
		for (let i = 0; i < fileParts.length; i++) {
			if (fileParts[i] === undefined) {
				console.error(`Missing part ${i+1} of file ${path}`);
				console.log(parts);
				return false;
			}
		}
	}
	
	return true;

}

// confirm compatibility with the update
async function updateIsCompatible(updateData) {
	updateProgress("Requesting compatibility check from board");
	const compatibility_data = {
		update_file_format: updateData.update_file_format,
		supported_hardware: updateData.supported_hardware,
		micropython_versions: updateData.micropython_versions,
		supported_software_versions: updateData.supported_software_versions,
		version: updateData.version
	};
	const response = await window.smartFetch("/api/update/validate_compatibility", compatibility_data, true);
	const status = await response.status;
	
	if (status !== 200) {
		console.error("Failed to validate update compatibility:", status);
		return false;
	}
	return true;
}

// Filter list of files to only include changed files
async function generateFileIndex(updateData) {
	const chunk_size = updateData.chunk_size;
	const server_index_response = await window.smartFetch("/api/update/file_index", { chunk_size }, true);

	if (server_index_response.status !== 200) {
		console.error("Failed to get server file index:", server_index_response.status);
		alert("Failed to get server file index.");
		return;
	}
	const serverFileIndex = await server_index_response.json();

	// convert updateData.files to a map of checksums by path
	const updateFileIndex = {};
	for (const file of updateData.files) {
		if (!updateFileIndex[file.path]) {
			let parts;
			// make list the length of the number of parts
			if (!file.final_bytes) {
				parts = 1;
			} else {
				parts = Math.ceil(file.final_bytes / chunk_size);
			}
			updateFileIndex[file.path] = new Array(parts);
		}
		// insert the checksum by part number
		updateFileIndex[file.path][file.part-1] = file.checksum;
	}

	// TODO always include files with execute=True

	// "zip" the two indexes together with true/false for each part of each file
	// true if the checksums don't match and we need to upload this part
	// false if the checksums match and we don't need to upload this part
	// or if this part is after a part that was different
	const changedParts = {};
	for (const path in updateFileIndex) {
		const updateChecksums = updateFileIndex[path];
		const serverChecksums = serverFileIndex[path];
		if (!serverChecksums) {
			// this file is new
			changedParts[path] = updateChecksums.map(() => true);
			continue;
		}

		const changedPartsForFile = [];
		for (let i = 0; i < updateChecksums.length; i++) {
			if (updateChecksums[i] !== serverChecksums[i]) {
				// fill in the rest of the parts as changed
				for (let j = i; j < updateChecksums.length; j++) {
					changedPartsForFile.push(true);
				}
				continue;
			} else {
				changedPartsForFile.push(false);
				// log that we are skipping this part
				updateProgress(`${path} part ${i+1} of ${updateChecksums.length} checksum matches`, 2);
				// sleep for one tenth of a second to allow the progress bar to update
				await new Promise(resolve => setTimeout(resolve, 20));
			}
		}
		changedParts[path] = changedPartsForFile;
	}


	// filter original updateData.files to only include changed files
	const changedFiles = updateData.files.filter((file) => {
		return changedParts[file.path][file.part-1];
	});

	return changedFiles;
}


// Upload only changed files
async function uploadFiles(files, chunk_size) {
	for (const file of files) {
		let parts;
		// make list the length of the number of parts
		if (!file.final_bytes) {
			parts = 1;
		} else {
			parts = Math.ceil(file.final_bytes / chunk_size);
		}
		updateProgress(`Uploading ${file.path} (${file.part} of ${parts} parts)`, 2);
		const response = await window.smartFetch("/api/update/file_part", file, true);
		if (response.status !== 200) {
			console.error(`Failed to upload file ${file.path}, part ${file.part} of ${parts}:`, response.status, response.statusText)
			console.error(response);
			//TODO retry the upload?
			//TODO restart the update process? we don't know if this file is corrupted now
			//TODO send over checksums in the hopes that the server can walk back the changes so we can try again
			alert(`Failed to upload file ${file.path}, part ${file.part} of ${parts}.`);
		}
	}
}

// Handle the update process
window.applyUpdate = async function (file) {
	const fileText = await file.text();
	const updateData = await JSON.parse(fileText);

	// Step 0: setup the update progress modal
	let num_files = 70;
	try {
		num_files = updateData.files.length;
	} catch (error) {
		console.error("Failed to get number of files in update:", error);
	}
	
	const estimated_seconds = (
		2 + // validate update locally
		10 + // confirm compatibility on board
		18 + // generate file index
		num_files * 4 + // upload files
		18 + // confirm the update
		20 // buffer
	);
	updateProgress("Initializing Update", 0, 0, estimated_seconds);

	const update_progress_modal = document.getElementById('update-progress-modal');
	update_progress_modal.showModal();
	
	// once per second, add a . to the log to show that the page is still alive
	// save it in a variable so we can stop it later
	const interval = setInterval(() => {
		document.getElementById('update-progress-log').innerText += '.';
	}, 1000);
		

	// Step 1: Validate the update file
	const valid_update = await update_file_is_valid(updateData);
	if (!valid_update){
		alert("This file does not appear to be a valid update.");
		return;
	}

	// Step 2: Confirm update compatibility
	if (!await updateIsCompatible(updateData)) {
		alert("This file does not appear to be a valid update.", response.statusText);
		return;
	}
	console.log("Update is compatible.");

	// Step 3: Generate file index and get server's file state
	updateProgress("Requesting server file checksums (may take a few seconds)", 18);
	const serverFileIndex = await generateFileIndex(updateData);
	// second progress bar step to make the main "progress" happen after the call to the server

	// Step 4: Upload changed files
	await uploadFiles(serverFileIndex, updateData.chunk_size);

	// Step 5: Confirm the update
	// check the final full checksum of file system by redoing step 2 and expecting no changes
	// with the exception of files that were marked as execute=True
	updateProgress("Validating update (may take a few seconds)", 18);
	const finalFileIndex = await generateFileIndex(updateData);
	const paths_with_execute = updateData.files.filter((file) => {
		return file.execute;
	}).map((file) => {
		return file.path;
	});
	
	// check that the finalFileIndex is the same as the serverFileIndex except for files with execute=True
	for (const path in finalFileIndex) {
		if (paths_with_execute.includes(path)) {
			continue;
		}
		if (finalFileIndex[path] !== serverFileIndex[path]) {
			console.error("Failed to apply update: checksums do not match after upload:", path, finalFileIndex[path], serverFileIndex[path]);
			alert("Failed to apply update.");
			return;
		}
	}
	// second progress bar step to make the main "progress" happen after the call to the server
	
	// Step 6: Reboot the device
	updateProgress("Update complete", 1, 1, 1);

	// stop adding .s to the log
	clearInterval(interval);

	// TODO enable "finalize" button which calls reboot
	// await window.smartFetch("/api/settings/reboot", null, true);
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
		console.log("Applying update...");
		await window.applyUpdate(file);
		fileInput.disabled = false;
		fileInput.value = ""; // Clear the input after processing
	});
};

// function for updating the update progress modal
window.updateProgress = function (log_msg, increment_value=1, set_value=false, max=false) {
	const progress_bar = document.getElementById('update-progress-bar');
	const progress_log = document.getElementById('update-progress-log');

	if (max) {
		progress_bar.max = max;
	}

	if (increment_value) {
		progress_bar.value += increment_value;
	}
	if (set_value) {
		progress_bar.value = set_value;
	}
	
	
	// this is a seperate call to prevent any possible xss issues
	progress_log.appendChild(document.createElement('br'));
	// append log message to the log element with a <br> at the end
	progress_log.innerText += log_msg.replace(/ /g, '\u00A0') + ' '; // add space to encourage wrapping

	// automatically scroll the log to the bottom
	progress_log.scroll({
		top: progress_log.scrollHeight,
		behavior: 'smooth'
	});

	console.log(log_msg);
}


