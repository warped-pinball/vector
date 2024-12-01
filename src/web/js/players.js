function populateTable(data) {
    const tbody = document.querySelector('table tbody');
    tbody.innerHTML = ''; // Clear existing rows

    const maxPlayers = 20;
    const players = Object.values(data);

    for (let i = 0; i < maxPlayers; i++) {
        const player = players[i] || { initials: '', name: '' };
        const row = document.createElement('tr');

        const initialsCell = document.createElement('td');
        const initialsInput = document.createElement('input');
        initialsInput.type = 'text';
        initialsInput.value = player.initials;
        initialsCell.appendChild(initialsInput);
        row.appendChild(initialsCell);

        const nameCell = document.createElement('td');
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.value = player.name;
        nameCell.appendChild(nameInput);
        row.appendChild(nameCell);

        const saveCell = document.createElement('td');
        const saveButton = document.createElement('button');
        saveButton.textContent = 'Save';
        saveButton.addEventListener('click', () => savePlayer(i, initialsInput.value, nameInput.value));
        saveCell.appendChild(saveButton);
        row.appendChild(saveCell);

        tbody.appendChild(row);
    }
}

function savePlayer(id, initials, name) {
    fetch('/updatePlayer', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ id: id, initials: initials, name: name })
    }).then(response => response.json())
      .then(data => {
          console.log('Success:', data);
          fetch('/players')
              .then(response => response.json())
              .then(data => populateTable(data))
              .catch(error => console.error('Error fetching player data:', error));
      })
      .catch(error => console.error('Error:', error));
}

fetch('/players')
.then(response => response.json())
.then(data => populateTable(data))
.catch(error => console.error('Error fetching player data:', error));
