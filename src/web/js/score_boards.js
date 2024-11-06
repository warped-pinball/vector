// Generic function to update a table with cached data and fetch new data from the server
function updateTable(tableId, endpoint, minRows = 4) {
    const tableBody = document.getElementById(tableId).getElementsByTagName('tbody')[0];

    // Function to create and populate a row
    function createRow(rank, initials = "", fullName = "", score = "", date = "") {
        let row = tableBody.insertRow();
        row.insertCell(0).innerText = rank;
        row.insertCell(1).innerText = score.toLocaleString ? score.toLocaleString() : score;
        row.insertCell(2).innerText = initials;
        row.insertCell(3).innerText = fullName;
        row.insertCell(4).innerText = date;

        // Optional styling for first place
        if (rank === 1) {
            row.setAttribute("data-theme", "light");
        }
    }

    // Load data from cache
    const cachedData = JSON.parse(localStorage.getItem(endpoint));
    if (cachedData) {
        // Clear existing rows and populate table with cached data
        tableBody.innerHTML = '';
        cachedData.forEach((item, index) => {
            createRow(index + 1, item.initials, item.full_name, item.score, item.date);
        });
        // Fill blank rows if fewer than minRows are present
        for (let i = cachedData.length; i < minRows; i++) {
            createRow(i + 1);
        }
    }

    // Fetch new data from the server
    fetch(endpoint)
        .then(response => response.json())
        .then(data => {
            // Update cache with new data
            localStorage.setItem(endpoint, JSON.stringify(data));
            tableBody.innerHTML = ''; // Clear existing rows

            // Populate table with the new data
            data.forEach((item, index) => {
                createRow(index + 1, item.initials, item.full_name, item.score, item.date);
            });

            // Add blank rows if fewer than minRows are present
            for (let i = data.length; i < minRows; i++) {
                createRow(i + 1);
            }
        })
        .catch(error => {
            console.error(`Failed to load data for ${tableId} from ${endpoint}:`, error);
        });
}

// Wrapper functions for each table to keep it simple
function updateLeaderboard() {
    updateTable('leaderboardTable', '/leaderboard');
}

function updateTournament() {
    updateTable('tournamentTable', '/tournament');
}

function updatePersonal() {
    updateTable('personalTable', '/personal');
}

// Auto-refresh intervals
const leaderboardIntervalId = setInterval(updateLeaderboard, 60000);
const tournamentIntervalId = setInterval(updateTournament, 60000);
const personalIntervalId = setInterval(updatePersonal, 60000);

// Cleanup function to clear intervals when needed
window.cleanupTables = function() {
    clearInterval(leaderboardIntervalId);
    clearInterval(tournamentIntervalId);
    clearInterval(personalIntervalId);
};

// Toggle table visibility and trigger update function for the selected table
function toggleTable(tableId) {
    // Hide all table containers
    document.getElementById('leaderboardContainer').style.display = 'none';
    document.getElementById('tournamentContainer').style.display = 'none';
    document.getElementById('personalContainer').style.display = 'none';

    // Show the selected table's container
    const selectedContainer = document.getElementById(tableId + 'Container');
    if (selectedContainer) {
        selectedContainer.style.display = 'block';

        // Trigger the update function for the visible table
        if (tableId === 'leaderboardTable') {
            updateLeaderboard();
        } else if (tableId === 'tournamentTable') {
            updateTournament();
        } else if (tableId === 'personalTable') {
            updatePersonal();
        }
    } else {
        console.error("Container not found for tableId:", tableId);
    }

    // Update active button styles
    const buttons = document.querySelectorAll('.score-board nav button');
    buttons.forEach(button => button.classList.remove('active'));

    // Add the 'active' class to the correct button
    const activeButton = document.querySelector(`button[onclick="toggleTable('${tableId}')"]`);
    if (activeButton) {
        activeButton.classList.add('active');
    } else {
        console.error("Button not found for tableId:", tableId);
    }
}

// Set up navigation buttons and initialize with default table
document.addEventListener('tablesLoaded', function () {
    document.getElementById('navigate-score-boards').addEventListener('click', () => toggleTable('leaderboardTable'));
    document.getElementById('navigate-tournament').addEventListener('click', () => toggleTable('tournamentTable'));
    document.getElementById('navigate-personal-board').addEventListener('click', () => toggleTable('personalTable'));

    // Show the leaderboard table by default
    toggleTable('leaderboardTable');
});
