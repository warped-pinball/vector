/* scores.js */

// Global variable for the current auto-refresh interval
window.currentRefreshIntervalId = null;

/*
 * Function: renderArticleList
 * Renders an array of data items as <article> rows into a given container.
 * Each article gets child <div> cells with class names matching the column keys.
 */
window.renderArticleList = function(containerId, data, columns, sortColumnIndex, sortDirection) {
    var sortKey = columns[sortColumnIndex] ? columns[sortColumnIndex].key : null;
    if (sortKey) {
        data.sort(function(a, b) {
            var aVal = a[sortKey];
            var bVal = b[sortKey];
            var aNum = parseFloat(aVal);
            var bNum = parseFloat(bVal);
            var comparison = 0;
            if (!isNaN(aNum) && !isNaN(bNum)) {
                comparison = aNum - bNum;
            } else {
                var aStr = (aVal || '').toString();
                var bStr = (bVal || '').toString();
                comparison = aStr.localeCompare(bStr, undefined, { numeric: true, sensitivity: 'base' });
            }
            return sortDirection === 'asc' ? comparison : -comparison;
        });
    }

    var container = document.getElementById(containerId);
    if (!container) {
        return;
    }
    container.innerHTML = '';
    data.forEach(function(item) {
        var articleRow = document.createElement('article');
        articleRow.classList.add('score-row');
        columns.forEach(function(col) {
            var cellValue = item[col.key] !== undefined ? item[col.key] : "";
            if (typeof cellValue === 'number' && cellValue.toLocaleString) {
                cellValue = cellValue.toLocaleString();
            }
            var cellDiv = document.createElement('div');
            cellDiv.classList.add(col.key);
            cellDiv.innerText = cellValue;
            articleRow.appendChild(cellDiv);
        });
        container.appendChild(articleRow);
    });
};

/*
 * Function: updateLeaderboardArticles
 * Fetches leaderboard data from the API and renders it as articles.
 */
window.updateLeaderboardArticles = function() {
    var leaderboardColumns = [
        { header: "Rank", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Initials", key: "initials" },
        { header: "Full Name", key: "full_name" },
        { header: "Date", key: "date" }
    ];

    var container = document.getElementById("leaderboardArticles");
    if (!container) {
        if (window.currentRefreshIntervalId) {
            clearInterval(window.currentRefreshIntervalId);
            window.currentRefreshIntervalId = null;
        }
        return;
    }

    fetch('/api/leaders')
        .then(function(response) {
            if (!response.ok) {
                throw new Error("Network response was not ok: " + response.statusText);
            }
            return response.json();
        })
        .then(function(data) {
            localStorage.setItem('/api/leaders', JSON.stringify(data));
            window.renderArticleList("leaderboardArticles", data, leaderboardColumns, 1, 'desc');
        })
        .catch(function(error) {
            console.error("Error fetching leaderboard data:", error);
        });
};

/*
 * Function: updateTournamentArticles
 * Fetches tournament data from the API and renders it as articles.
 */
window.updateTournamentArticles = function() {
    var tournamentColumns = [
        { header: "Game #", key: "game" },
        { header: "Rank", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Initials", key: "initials" }
    ];

    var container = document.getElementById("tournamentArticles");
    if (!container) {
        if (window.currentRefreshIntervalId) {
            clearInterval(window.currentRefreshIntervalId);
            window.currentRefreshIntervalId = null;
        }
        return;
    }

    fetch('/api/tournament')
        .then(function(response) {
            if (!response.ok) {
                throw new Error("Network response was not ok: " + response.statusText);
            }
            return response.json();
        })
        .then(function(data) {
            localStorage.setItem('/api/tournament', JSON.stringify(data));
            window.renderArticleList("tournamentArticles", data, tournamentColumns, 1, 'desc');
        })
        .catch(function(error) {
            console.error("Error fetching tournament data:", error);
        });
};

/*
 * Function: updatePersonalArticles
 * Fetches personal score data for the selected player and renders it as articles.
 */
window.updatePersonalArticles = function() {
    var playerSelect = document.getElementById('players');
    if (!playerSelect) {
        if (window.currentRefreshIntervalId) {
            clearInterval(window.currentRefreshIntervalId);
            window.currentRefreshIntervalId = null;
        }
        return;
    }
    var player_id = playerSelect.value;
    if (!player_id) return;

    var personalColumns = [
        { header: "Rank", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Date", key: "date" },
        { header: "Initials", key: "initials" },
        { header: "Name", key: "full_name" }
    ];

    var container = document.getElementById("personalArticles");
    if (!container) {
        if (window.currentRefreshIntervalId) {
            clearInterval(window.currentRefreshIntervalId);
            window.currentRefreshIntervalId = null;
        }
        return;
    }

    fetch('/api/player/scores?id=' + player_id)
        .then(function(response) {
            if (!response.ok) {
                throw new Error("Network response was not ok: " + response.statusText);
            }
            return response.json();
        })
        .then(function(data) {
            localStorage.setItem('/api/player/scores?id=' + player_id, JSON.stringify(data));
            window.renderArticleList("personalArticles", data, personalColumns, 1, 'desc');
        })
        .catch(function(error) {
            console.error("Error fetching personal scores:", error);
        });
};

/*
 * Function: loadPlayers
 * Loads player data into the personal board dropdown and sets up a change listener.
 */
window.loadPlayers = function(data) {
    var players = Object.entries(data)
        .filter(function(entry) {
            var player = entry[1];
            return player.name.trim() !== '' || player.initials.trim() !== '';
        })
        .sort(function(a, b) {
            return a[1].name.localeCompare(b[1].name);
        });
    var playersSelect = document.getElementById('players');
    if (!playersSelect) {
        return;
    }
    playersSelect.innerHTML = '';
    players.forEach(function(entry) {
        var id = entry[0];
        var player = entry[1];
        var option = document.createElement('option');
        option.value = id;
        option.text = player.name + (player.initials ? " (" + player.initials + ")" : "");
        playersSelect.appendChild(option);
    });
    if (players.length > 0) {
        playersSelect.value = players[0][0];
        window.updatePersonalArticles();
    }
    playersSelect.addEventListener('change', function() {
        window.updatePersonalArticles();
    });
};

/*
 * Auto-Refresh Mechanism:
 * Only the currently visible board is auto-refreshed every 60 seconds.
 */
var refreshFunctions = {
    "leader-board": window.updateLeaderboardArticles,
    "tournament-board": window.updateTournamentArticles,
    "personal-board": window.updatePersonalArticles
};

window.startAutoRefreshForTab = function(tabId) {
    if (window.currentRefreshIntervalId) {
        clearInterval(window.currentRefreshIntervalId);
        window.currentRefreshIntervalId = null;
    }
    var containerId = "";
    if (tabId === "leader-board") containerId = "leaderboardArticles";
    else if (tabId === "tournament-board") containerId = "tournamentArticles";
    else if (tabId === "personal-board") containerId = "personalArticles";

    var container = document.getElementById(containerId);
    if (!container) {
        return;
    }
    var refreshFn = refreshFunctions[tabId];
    window.currentRefreshIntervalId = setInterval(function() {
        var currentContainer = document.getElementById(containerId);
        if (currentContainer) {
            refreshFn();
        } else {
            clearInterval(window.currentRefreshIntervalId);
            window.currentRefreshIntervalId = null;
        }
    }, 60000);
};

/*
 * Function: showTab
 * Hides all tabs, shows the selected tab, updates active button styling,
 * immediately updates the tab’s data, and starts auto-refresh for it.
 */
window.showTab = function(tabId) {
    // Hide all tab contents
    var tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(function(tab) {
        tab.classList.remove('active');
    });
    // Show the selected tab
    var selectedTab = document.getElementById(tabId);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }
    // Update active button styling
    var buttons = document.querySelectorAll('#score-board-nav button');
    buttons.forEach(function(button) {
        button.classList.remove('contrast');
    });
    var activeButton = document.querySelector('button[onclick="window.showTab(\'' + tabId + '\')"]');
    if (activeButton) {
        activeButton.classList.add('contrast');
    }
    // Immediately update the visible tab’s data
    if (tabId === "leader-board") {
        window.updateLeaderboardArticles();
    } else if (tabId === "tournament-board") {
        window.updateTournamentArticles();
    } else if (tabId === "personal-board") {
        window.updatePersonalArticles();
    }
    // Start auto-refresh for the visible tab
    window.startAutoRefreshForTab(tabId);
};

/*
 * Function: cleanupRefreshes
 * Clears any active auto-refresh interval.
 */
window.cleanupRefreshes = function() {
    if (window.currentRefreshIntervalId) {
        clearInterval(window.currentRefreshIntervalId);
        window.currentRefreshIntervalId = null;
    }
};

/*
 * Polling for Elements:
 * Since the DOM load events aren’t reliably detected in your setup,
 * we poll until the main leaderboard element becomes available.
 * Once it is, we immediately pull the leaderboard (the default),
 * start auto-refresh, and load the players.
 */
(function pollForElements() {
    if (document.getElementById("leaderboardArticles") && document.getElementById("score-board-nav")) {
        // Default to the leaderboard
        window.updateLeaderboardArticles();
        window.startAutoRefreshForTab("leader-board");
        // Load the players for the personal board dropdown
        fetch('/api/players')
            .then(function(response) {
                return response.json();
            })
            .then(function(data) {
                window.loadPlayers(data);
            })
            .catch(function(error) {
                console.error("Error fetching players:", error);
            });
    } else {
        setTimeout(pollForElements, 100);
    }
})();
