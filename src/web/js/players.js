function createInputField(type, name, value, placeholder, onInput) {
    const input = document.createElement('input');
    input.type = type;
    input.name = name;
    input.value = value;
    input.placeholder = placeholder;
    input.addEventListener('input', onInput);
    return input;
}

function getCurrentPlayers(data) {
    return Object.entries(data)
        .filter(([, player]) => player.name.trim() !== '' || player.initials.trim() !== '')
        .sort(([, a], [, b]) => a.name.localeCompare(b.name));
}

function getAvailableIndex(allIndices, maxIndex) {
    const indicesSet = new Set(allIndices);
    for (let i = 1; i <= maxIndex; i++) {
        if (!indicesSet.has(i)) {
            return i;
        }
    }
    return maxIndex + 1;
}

function addPlayerRow(form, index, initials, name) {
    const fieldset = document.createElement('fieldset');
    fieldset.setAttribute('role', 'group');
    fieldset.dataset.index = index;

    const onInput = () => toggleSaveButton(fieldset, initials, name);

    const initialsInput = createInputField('text', 'initials', initials, 'Initials', onInput);
    const nameInput = createInputField('text', 'name', name, 'Full Name', onInput);

    fieldset.appendChild(initialsInput);
    fieldset.appendChild(nameInput);

    // add the save button hidden with the "hide" class
    const saveButton = document.createElement('input');
    saveButton.type = 'button';
    saveButton.value = 'Save';
    saveButton.classList.add('hide');
    saveButton.addEventListener('click', () => {
        const index = fieldset.dataset.index;
        savePlayer(index, initialsInput.value, nameInput.value);
    });
    fieldset.appendChild(saveButton);

    // Only show the delete button if the player has initials or a name
    if (initials.trim() !== '' || name.trim() !== '') {
        const deleteButton = document.createElement('input');
        deleteButton.type = 'button';
        deleteButton.classList.add('secondary');
        deleteButton.value = 'Delete';
        deleteButton.addEventListener('click', () => savePlayer(index, '', ''));
        fieldset.appendChild(deleteButton);
    }

    form.appendChild(fieldset);
}

function toggleSaveButton(fieldset) {
    const saveButton = fieldset.querySelector('input[type="button"]');
    const initialsInput = fieldset.querySelector('input[name="initials"]');
    const nameInput = fieldset.querySelector('input[name="name"]');
    const deleteButton = fieldset.querySelector('input[value="Delete"]');
    const initials = initialsInput.value;
    const name = nameInput.value;

    if (initials.trim() === '' && name.trim() === '') {
        saveButton.classList.add('hide');
        if (deleteButton) {
            deleteButton.classList.remove('hide');
        }
    } else {
        saveButton.classList.remove('hide');
        if (deleteButton) {
            deleteButton.classList.add('hide');
        }
    }
}

async function savePlayer(index, initials, name) {
    console.log('Saving player:', index, initials, name);
    const data = {
        "id": index,
        "initials": initials,
        "full_name": name
    };

    try {
        const response = await window.smartFetch('/api/player/update', data, true);

        if (response.status !== 200) {
            console.error('Failed to save player:', response.status);
            return;
        }

        populateForm();
    } catch (error) {
        console.error('Error saving player:', error);
    }
}

async function populateForm() {
    try {
        const response = await window.smartFetch('/api/players', false, false);
        const data = await response.json();

        const form = document.getElementById('players_form');
        form.innerHTML = '';

        const players = getCurrentPlayers(data);
        const allIndices = Object.keys(data).map(index => parseInt(index, 10));

        players.forEach(([index, player]) => {
            addPlayerRow(form, index, player.initials, player.name);
        });

        if (players.length < 30) {
            const extraRowIndex = getAvailableIndex(allIndices, 30); // Adjusted to 30
            addPlayerRow(form, extraRowIndex, '', '');
        }
    } catch (error) {
        console.error('Error fetching player data:', error);
    }
}

populateForm();
