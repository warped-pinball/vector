// Observe the html[data-theme] attribute and update the top row theme accordingly
function observeThemeChanges(tableId) {
    const htmlElement = document.documentElement;
    const observer = new MutationObserver(() => {
        updateTopRowTheme(tableId);
    });
    observer.observe(htmlElement, { attributes: true, attributeFilter: ['data-theme'] });
}

// Update the theme of the top row based on the opposite of the current html theme
function updateTopRowTheme(tableId) {
    const htmlTheme = document.documentElement.getAttribute("data-theme") || "light";
    const table = document.getElementById(tableId);
    if (!table) return;
    const tbody = table.getElementsByTagName('tbody')[0];
    if (!tbody) return;

    // Clear any theme attributes first
    Array.from(tbody.rows).forEach(row => row.removeAttribute("data-theme"));

    // Apply opposite theme to the first row if it exists
    const firstRow = tbody.rows[0];
    if (firstRow) {
        const oppositeTheme = (htmlTheme === "dark") ? "light" : "dark";
        firstRow.setAttribute("data-theme", oppositeTheme);
    }
}

// Render the table with given data, columns, sorting, etc.
function renderTable(tableId, data, columns, sortColumnIndex, sortDirection, minRows = 4) {
    const table = document.getElementById(tableId);
    if (!table) {
        console.error("Table not found:", tableId);
        return;
    }
    const tableBody = table.getElementsByTagName('tbody')[0];
    tableBody.innerHTML = '';

    // Sort the data if requested
    // Determine the key to sort by
    const sortKey = columns[sortColumnIndex]?.key;
    if (sortKey) {
        data.sort((a, b) => {
            const aVal = a[sortKey];
            const bVal = b[sortKey];

            // Decide on sort behavior: if numeric, compare as number; else compare as string
            const aNum = parseFloat(aVal);
            const bNum = parseFloat(bVal);
            let comparison = 0;

            if (!isNaN(aNum) && !isNaN(bNum)) {
                comparison = aNum - bNum;
            } else {
                const aStr = (aVal || '').toString();
                const bStr = (bVal || '').toString();
                comparison = aStr.localeCompare(bStr, undefined, {numeric: true, sensitivity: 'base'});
            }

            return sortDirection === 'asc' ? comparison : -comparison;
        });
    }

    // Create rows for the actual data
    data.forEach((item, index) => {
        const row = tableBody.insertRow();
        columns.forEach(col => {
            let cellValue = item[col.key] !== undefined ? item[col.key] : "";
            if (typeof cellValue === 'number' && cellValue.toLocaleString) {
                cellValue = cellValue.toLocaleString();
            }
            const cell = row.insertCell();
            cell.innerText = cellValue;
        });
    });

    // Update the top row theme after rendering
    updateTopRowTheme(tableId);
}

// This function updates the table given pre-fetched data
function updateTableWithData(tableId, data, columns, sortColumnIndex = 0, sortDirection = 'asc', minRows = 4) {
    renderTable(tableId, data, columns, sortColumnIndex, sortDirection, minRows);
}

// This function fetches data from the endpoint and then updates the table
async function fetchDataAndUpdateTable(tableId, endpoint, columns, sortColumnIndex = 0, sortDirection = 'asc', minRows = 4) {
    // Try using cached data first
    const cachedData = JSON.parse(localStorage.getItem(endpoint));
    if (cachedData) {
        updateTableWithData(tableId, cachedData, columns, sortColumnIndex, sortDirection, minRows);
    }

    // Fetch fresh data
    try {
        const response = await fetch(endpoint);
        if (!response.ok) {
            console.warn(`Failed to fetch data from ${endpoint}: ${response.statusText}`);
            return;
        }
        const data = await response.json();
        localStorage.setItem(endpoint, JSON.stringify(data));
        updateTableWithData(tableId, data, columns, sortColumnIndex, sortDirection, minRows);
    } catch (error) {
        console.error(`Failed to load data for ${tableId} from ${endpoint}:`, error);
    }
}

// Example usage functions
function updateLeaderboard() {
    const leaderboardColumns = [
        { header: "Rank", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Initials", key: "initials" },
        { header: "Full Name", key: "full_name" },
        { header: "Date", key: "date" }
    ];
    fetchDataAndUpdateTable('leaderboardTable', '/api/leaders', leaderboardColumns, 1, 'desc', 4);
}

function updateTournament() {
    const tournamentColumns = [
        { header: "Game #", key: "game" },
        { header: "Rank", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Initials", key: "initials" },
    ];
    fetchDataAndUpdateTable('tournamentTable', '/api/tournament', tournamentColumns, 1, 'desc', 4);
}

function updatePersonal() {
    const player_id = document.getElementById('players').value;
    if (!player_id) return;

    const personalColumns = [
        { header: "Score", key: "score" },
        { header: "Date", key: "date" }
    ];

    fetchDataAndUpdateTable('personalTable', `/api/player/scores?id=${player_id}`, personalColumns, 0, 'desc', 4);
    const player_name = document.getElementById('players').selectedOptions[0].text;
    document.getElementById('personal_scoreboard_caption').innerText = `personal_${player_name}`;
}

// Load players for dropdown
async function loadPlayers(data) {
    const players = Object.entries(data)
        .filter(([ , player]) => player.name.trim() !== '' || player.initials.trim() !== '')
        .sort(([, a], [, b]) => a.name.localeCompare(b.name));
    
    const playersSelect = document.getElementById('players');
    playersSelect.innerHTML = '';
    players.forEach(player => {
        const option = document.createElement('option');
        option.value = player[0];
        option.text = player[1].name + " " + (player[1].initials ? `(${player[1].initials})` : '');
        playersSelect.appendChild(option);
    });

    if (players.length > 0) {
        playersSelect.value = players[0][0];
        updatePersonal()
    }

    playersSelect.addEventListener('change', async function () {
        updatePersonal()
    });
}

// Initial fetch to populate the player form
fetch('/api/players')
    .then(response => response.json())
    .then(data => loadPlayers(data))
    .catch(error => console.error('Error fetching player data:', error));

// Auto-refresh intervals
try {
    const leaderboardIntervalId = setInterval(updateLeaderboard, 60000); // Update every minute
    const tournamentIntervalId = setInterval(updateTournament, 60000); // Update every minute
    const personalIntervalId = setInterval(updatePersonal, 60000); // Update every minute

    // Store interval IDs globally so we can clear them later if needed
    window.leaderboardIntervalId = leaderboardIntervalId;
    window.tournamentIntervalId = tournamentIntervalId;
    window.personalIntervalId = personalIntervalId;
} catch (error) {
    console.log('intervals already defined');
}
updateLeaderboard();
updateTournament();
updatePersonal();

// Cleanup function to clear intervals when needed
window.cleanupTables = function() {
    clearInterval(window.leaderboardIntervalId);
    clearInterval(window.tournamentIntervalId);
    clearInterval(window.personalIntervalId);
};

// Toggle table visibility
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

// Show tab
function showTab(tabId) {
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    document.getElementById(tabId).classList.add('active');

    document.querySelectorAll('#score-board-nav button').forEach(
        button => button.classList.remove('contrast')
    );
    const activeButton = document.querySelector(`button[onclick="showTab('${tabId}')"]`);
    if (activeButton) activeButton.classList.add('contrast');
}

// Begin observing theme changes for tables that need it
// Add any table IDs here that should re-check their first row theme upon theme changes
observeThemeChanges('leaderboardTable');
observeThemeChanges('tournamentTable');
observeThemeChanges('personalTable');
