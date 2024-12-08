function getCurrentPlayers(data) {
    return Object.entries(data)
        .filter(([index, player]) => player.name.trim() !== '' || player.initials.trim() !== '')
        .sort(([, a], [, b]) => a.name.localeCompare(b.name)); // Sort by name alphabetically
}

function populateForm(data) {
    const form = document.getElementById('players_form');
    form.innerHTML = ''; // Clear existing form groups

    const players = getCurrentPlayers(data);
    const allIndices = Object.keys(data).map(index => parseInt(index, 10));

    // Populate form with existing players
    players.forEach(([index, player]) => {
        addPlayerRow(form, index, player.initials, player.name);
    });

    // Always add one extra blank form group for new players
    const extraRowIndex = getAvailableIndex(allIndices, 20); // Get the lowest available index under 20
    addPlayerRow(form, extraRowIndex, '', '');
}

function addPlayerRow(form, index, initials, name) {
    const fieldset = document.createElement('fieldset');
    fieldset.setAttribute('role', 'group');
    fieldset.dataset.index = index; // Assign the index as a data attribute

    const initialsInput = document.createElement('input');
    initialsInput.type = 'text';
    initialsInput.name = 'initials';
    initialsInput.value = initials;
    initialsInput.placeholder = 'Initials';
    initialsInput.addEventListener('input', () => toggleSaveButton(fieldset, initials, name));
    fieldset.appendChild(initialsInput);

    const nameInput = document.createElement('input');
    nameInput.type = 'text';
    nameInput.name = 'name';
    nameInput.value = name;
    nameInput.placeholder = 'Full Name';
    nameInput.addEventListener('input', () => toggleSaveButton(fieldset, initials, name));
    fieldset.appendChild(nameInput);

    form.appendChild(fieldset);
}

function getAvailableIndex(allIndices, maxIndex) {
    // Find the first available index under maxIndex
    for (let i = 1; i <= maxIndex; i++) {
        if (!allIndices.includes(i)) {
            return i;
        }
    }
    // If all indices are used, return maxIndex + 1 to ensure a unique new index
    return maxIndex + 1;
}

function toggleSaveButton(fieldset, originalInitials = '', originalName = '') {
    const initialsInput = fieldset.querySelector('input[name="initials"]');
    const nameInput = fieldset.querySelector('input[name="name"]');
    let saveButton = fieldset.querySelector('input[type="button"]');

    if (initialsInput.value !== originalInitials || nameInput.value !== originalName) {
        if (!saveButton) {
            saveButton = document.createElement('input');
            saveButton.type = 'button';
            saveButton.value = 'Save';
            saveButton.addEventListener('click', () => {
                const index = fieldset.dataset.index; // Use the index from the dataset
                savePlayer(index, initialsInput.value, nameInput.value);
            });
            fieldset.appendChild(saveButton);
        }
    } else {
        if (saveButton) {
            saveButton.remove();
        }
    }
}

async function savePlayer(index, initials, name) {
    console.log('Saving player:', index, initials, name);
    console.log(JSON.stringify({ index: index, initials: initials, full_name: name }));
    try {
        const response = await fetch('/api/player/update', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ index: index, initials: initials, full_name: name }),
        });

        const message = await response.text();
        if (message !== 'Update successful') {
            throw new Error(`Error from server: ${message}`);
        }

        console.log('Success:', message);

        // Re-fetch and update the form
        const playersResponse = await fetch('/players');
        const playersData = await playersResponse.json();
        populateForm(playersData);
    } catch (error) {
        console.error('Error saving player:', error);
    }
}

// Initial fetch to populate the form
fetch('/api/players')
    .then(response => response.json())
    .then(data => populateForm(data))
    .catch(error => console.error('Error fetching player data:', error));
