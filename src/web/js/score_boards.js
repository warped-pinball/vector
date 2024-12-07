
// Generic function to update a table with cached data and fetch new data from the server
async function updateTable(tableId, endpoint, minRows = 4) {
    const tableBody = document.getElementById(tableId).getElementsByTagName('tbody')[0];

    function createRow(rank, initials = "", fullName = "", score = "", date = "") {
        let row = tableBody.insertRow();
        row.insertCell(0).innerText = rank;
        row.insertCell(1).innerText = score.toLocaleString ? score.toLocaleString() : score;
        row.insertCell(2).innerText = initials;
        row.insertCell(3).innerText = fullName;
        row.insertCell(4).innerText = date;
        if (rank === 1) {
            row.setAttribute("data-theme", "light");
        }
    }

    const cachedData = JSON.parse(localStorage.getItem(endpoint));
    if (cachedData) {
        tableBody.innerHTML = '';
        cachedData.forEach((item, index) => {
            createRow(index + 1, item.initials, item.full_name, item.score, item.date);
        });
        for (let i = cachedData.length; i < minRows; i++) {
            createRow(i + 1);
        }
    }

    try {
        const response = await fetch(endpoint);
        if (!response.ok) {
            console.warn(`Failed to fetch data from ${endpoint}: ${response.statusText}`);
            return; // Exit if there's an error like 404
        }

        const data = await response.json();
        localStorage.setItem(endpoint, JSON.stringify(data));
        tableBody.innerHTML = '';
        data.forEach((item, index) => {
            createRow(index + 1, item.initials, item.full_name, item.score, item.date);
        });
        for (let i = data.length; i < minRows; i++) {
            createRow(i + 1);
        }
    } catch (error) {
        console.error(`Failed to load data for ${tableId} from ${endpoint}:`, error);
    }
}

function updateLeaderboard() {
    updateTable('leaderboardTable', '/api/leaders');
}

function updateTournament() {
    updateTable('tournamentTable', '/api/tournament');
}

function updatePersonal() {
    //TODO implement this function
}

// Function to update individual scores
async function updateIndividualScores(player) {

    // check if the player is a number
    if (isNaN(player)) {
        console.error("Invalid player ID:", player);
        return;
    }

    const tableBody = document.getElementById('personalTable').getElementsByTagName('tbody')[0];
    const cachedScores = JSON.parse(localStorage.getItem(`indScores_${player}`));
    const playerNameElement = document.getElementById('player-name');

    if (playerNameElement && cachedScores) {
        tableBody.innerHTML = '';
        cachedScores.forEach(score => {
            const row = tableBody.insertRow();
            row.innerHTML = `<td>${score.score}</td><td>${score.date}</td>`;
        });
        playerNameElement.textContent = cachedScores[0]?.full_name || player;
    }

    try {
        const response = await fetch(`/api/player/scores?id=${player}`);
        if (!response.ok) {
            console.warn(`Failed to fetch scores for ${player}: ${response.statusText}`);
            return;
        }

        const scores = await response.json();
        localStorage.setItem(`indScores_${player}`, JSON.stringify(scores));
        tableBody.innerHTML = '';
        scores.forEach(score => {
            const row = tableBody.insertRow();
            row.innerHTML = `<td>${score.score}</td><td>${score.date}</td>`;
        });
        if (playerNameElement) {
            playerNameElement.textContent = scores[0]?.full_name || player;
        }
    } catch (error) {
        console.error(`Failed to load individual scores for ${player}:`, error);
    }
}

// Function to load player list for the dropdown
async function loadPlayers(data) {
    players = Object.entries(data)
        .filter(([index, player]) => player.name.trim() !== '' || player.initials.trim() !== '')
        .sort(([, a], [, b]) => a.name.localeCompare(b.name)); // Sort by name alphabetically
    
    const playersSelect = document.getElementById('players');
    playersSelect.innerHTML = '';
    players.forEach(player => {
        const option = document.createElement('option');
        option.value = player[0];
        option.text = player[1].name + " " + (player[1].initials ? `(${player[1].initials})` : '');
        playersSelect.appendChild(option);
    });

    if (players.length > 0) {
        playersSelect.value = players[0];
        await updateIndividualScores(players[0]);
    }

    playersSelect.addEventListener('change', async function () {
        const selectedPlayer = playersSelect.value;
        await updateIndividualScores(selectedPlayer);
    });

}



// Initial fetch to populate the form
fetch('/api/players')
    .then(response => response.json())
    .then(data => loadPlayers(data))
    .catch(error => console.error('Error fetching player data:', error));



// Auto-refresh intervals
// check if leaderboardIntervalId, tournamentIntervalId and personalIntervalId are not defined
try {
    const leaderboardIntervalId = setInterval(updateLeaderboard, 60000); // Update every minute
    const tournamentIntervalId = setInterval(updateTournament, 60000); // Update every minute
    const personalIntervalId = setInterval(updatePersonal, 60000); // Update every minute
} catch (error) {
    console.log('intervals already defined');
}
updateLeaderboard();
updateTournament();
updatePersonal();


// Cleanup function to clear intervals when needed
window.cleanupTables = function() {
    clearInterval(leaderboardIntervalId);
    clearInterval(tournamentIntervalId);
    clearInterval(personalIntervalId);
};

// Toggle table visibility and trigger update function for the selected table
function toggleTable(tableId) {
    document.getElementById('leaderboardContainer').style.display = 'none';
    document.getElementById('tournamentContainer').style.display = 'none';
    document.getElementById('personalContainer').style.display = 'none';

    const selectedContainer = document.getElementById(tableId + 'Container');
    if (selectedContainer) {
        selectedContainer.style.display = 'block';
        if (tableId === 'leaderboardTable') updateLeaderboard();
        else if (tableId === 'tournamentTable') updateTournament();
        else if (tableId === 'personalTable') updatePersonal();
    } else {
        console.error("Container not found for tableId:", tableId);
    }

    //  get all buttons in the div with id score-board-nav
    const buttons = document.querySelectorAll('#score-board-nav button');
    buttons.forEach(button => button.classList.remove('contrast'));
    const activeButton = document.querySelector(`button[onclick="toggleTable('${tableId}')"]`);
    if (activeButton) {
        activeButton.classList.add('contrast');
    } else {
        console.error("Button not found for tableId:", tableId);
    }
}

window.toggleTable = toggleTable;



function showTab(tabId) {
    // Hide all tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Show the selected tab
    document.getElementById(tabId).classList.add('active');

    // Update active button
    document.querySelectorAll('#score-board-nav button').forEach(
        button => button.classList.remove('contrast')
    );
    activeButton = document.querySelector(`button[onclick="showTab('${tabId}')"]`);
    activeButton.classList.add('contrast');
}