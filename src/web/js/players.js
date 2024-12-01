function populateForm(data) {
    const form = document.getElementById('players_form');
    form.innerHTML = ''; // Clear existing form groups

    const players = Object.entries(data); // Use entries to get index and player data

    players.forEach(([index, player]) => {
        const fieldset = document.createElement('fieldset');
        fieldset.setAttribute('role', 'group');
        fieldset.dataset.index = index; // Assign the index as a data attribute

        const initialsInput = document.createElement('input');
        initialsInput.type = 'text';
        initialsInput.name = 'initials';
        initialsInput.value = player.initials;
        initialsInput.placeholder = 'Initials';
        initialsInput.addEventListener('input', () => toggleSaveButton(fieldset, player.initials, player.name));
        fieldset.appendChild(initialsInput);

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.name = 'name';
        nameInput.value = player.name;
        nameInput.placeholder = 'Full Name';
        nameInput.addEventListener('input', () => toggleSaveButton(fieldset, player.initials, player.name));
        fieldset.appendChild(nameInput);

        form.appendChild(fieldset);
    });

    // Add an extra empty form group for new players
    const emptyFieldset = document.createElement('fieldset');
    emptyFieldset.setAttribute('role', 'group');

    const emptyInitialsInput = document.createElement('input');
    emptyInitialsInput.type = 'text';
    emptyInitialsInput.name = 'initials';
    emptyInitialsInput.placeholder = 'Initials';
    emptyInitialsInput.addEventListener('input', () => toggleSaveButton(emptyFieldset));
    emptyFieldset.appendChild(emptyInitialsInput);

    const emptyNameInput = document.createElement('input');
    emptyNameInput.type = 'text';
    emptyNameInput.name = 'name';
    emptyNameInput.placeholder = 'Full Name';
    emptyNameInput.addEventListener('input', () => toggleSaveButton(emptyFieldset));
    emptyFieldset.appendChild(emptyNameInput);

    form.appendChild(emptyFieldset);
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
                const index = fieldset.dataset.index || ''; // Default to empty for new players
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
        const response = await fetch('/updatePlayer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ index: index, initials: initials, full_name: name }),
        });

        if (!response.ok) {
            throw new Error(`Error: ${response.statusText}`);
        }

        const message = await response.text();
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
fetch('/players')
    .then(response => response.json())
    .then(data => populateForm(data))
    .catch(error => console.error('Error fetching player data:', error));
