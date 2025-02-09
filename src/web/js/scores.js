/* scores.js */

// Global variable for the current auto-refresh interval
window.currentRefreshIntervalId = null;

/*
 * Function: renderHeaderRow
 * Renders a header row (with column labels) into the specified container.
 */
window.renderHeaderRow = function (containerId, columns, colClass) {
    var container = document.getElementById(containerId);
    if (!container) return;
    var headerArticle = document.createElement('article');
    headerArticle.classList.add('header-row', colClass);

    // Render one cell per column
    columns.forEach(function (col) {
        var cellDiv = document.createElement('div');
        cellDiv.classList.add(col.key);
        cellDiv.innerText = col.header;
        headerArticle.appendChild(cellDiv);
    });

    container.insertBefore(headerArticle, container.firstChild);
};

/*
 * Function: renderDataRow
 * Renders one data row as an article with one cell per column.
 * For the "player" column, it combines "initials" and "full_name" if available.
 */
window.renderDataRow = function (item, columns, colClass) {
    var articleRow = document.createElement('article');
    articleRow.classList.add('score-row', colClass);

    columns.forEach(function (col) {
        var cellDiv = document.createElement('div');
        cellDiv.classList.add(col.key);

        var value = "";
        if (col.key === "player") {
            // Combine initials and full_name (if available)
            var initials = item["initials"] || "";
            var fullName = item["full_name"] || "";
            value = initials;
            if (fullName.trim() !== "") {
                value += " (" + fullName + ")";
            }
        } else {
            // For the rank column, we do not prepend "#"
            value = (item[col.key] !== undefined ? item[col.key] : "");
        }

        // Set text and a tooltip (title) so user sees full text on hover/long press
        cellDiv.innerText = value;
        cellDiv.setAttribute("title", value);

        articleRow.appendChild(cellDiv);
    });

    return articleRow;
};

/*
 * Function: renderFullArticleList
 * Clears the container and renders a header row followed by all data rows.
 */
window.renderFullArticleList = function (containerId, data, columns, colClass) {
    var container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = ''; // Clear previous content

    window.renderHeaderRow(containerId, columns, colClass);

    data.forEach(function (item) {
        var row = window.renderDataRow(item, columns, colClass);
        container.appendChild(row);
    });
};

/*
 * updateLeaderboardArticles: 5 columns => #, Score, Player, Ago, Date
 */
window.updateLeaderboardArticles = function () {
    var columns = [
        { header: "#", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Player", key: "player" },
        { header: "Ago", key: "ago" },
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
        .then(function (response) {
            if (!response.ok) {
                throw new Error("Network response was not ok: " + response.statusText);
            }
            return response.json();
        })
        .then(function (data) {
            localStorage.setItem('/api/leaders', JSON.stringify(data));
            window.renderFullArticleList("leaderboardArticles", data, columns, "five-col");
        })
        .catch(function (error) {
            console.error("Error fetching leaderboard data:", error);
        });
};

/*
 * updateTournamentArticles: 4 equally wide columns => Game, Rank, Initials, Score
 */
window.updateTournamentArticles = function () {
    var columns = [
        { header: "Game", key: "game" },
        { header: "Rank", key: "rank" },
        { header: "Initials", key: "initials" },
        { header: "Score", key: "score" }
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
        .then(function (response) {
            if (!response.ok) {
                throw new Error("Network response was not ok: " + response.statusText);
            }
            return response.json();
        })
        .then(function (data) {
            localStorage.setItem('/api/tournament', JSON.stringify(data));
            window.renderFullArticleList("tournamentArticles", data, columns, "four-col-tournament");
        })
        .catch(function (error) {
            console.error("Error fetching tournament data:", error);
        });
};

/*
 * updatePersonalArticles: 4 columns => #, Score, Ago, Date
 * Do nothing if no player is selected in our custom dropdown.
 */
window.updatePersonalArticles = function () {
    var container = document.getElementById("personalArticles");
    if (!container) {
        if (window.currentRefreshIntervalId) {
            clearInterval(window.currentRefreshIntervalId);
            window.currentRefreshIntervalId = null;
        }
        return;
    }

    // Read selected player ID from our custom dropdown
    var player_id = window.getDropDownValue("playerDropdown");
    // If user hasn't selected anything or default is empty => do nothing
    if (!player_id || player_id === "null") {
        console.log("No player selected, skipping personal scoreboard update.");
        container.innerHTML = '';
        return;
    }

    var columns = [
        { header: "#", key: "rank" },
        { header: "Score", key: "score" },
        { header: "Ago", key: "ago" },
        { header: "Date", key: "date" }
    ];

    fetch('/api/player/scores?id=' + player_id)
        .then(function (response) {
            if (!response.ok) {
                throw new Error("Network response was not ok: " + response.statusText);
            }
            return response.json();
        })
        .then(function (data) {
            localStorage.setItem('/api/player/scores?id=' + player_id, JSON.stringify(data));
            window.renderFullArticleList("personalArticles", data, columns, "four-col-personal");
        })
        .catch(function (error) {
            console.error("Error fetching personal scores:", error);
        });
};

/*
 * loadPlayers: build the new custom dropdown in #playerDropdownContainer.
 * DO NOT auto-load personal scoreboard. Wait until a player is chosen.
 */
window.loadPlayers = async function (data) {
    // "data" is presumably an object of ID -> { name, initials, ... }
    var playerDropdownContainer = document.getElementById('playerDropdownContainer');
    if (!playerDropdownContainer) return;

    // Build a { id: "PlayerName (INI)" } object for the dropdown
    var dropdownOptions = {};
    Object.entries(data).forEach(function ([id, player]) {
        var displayName = player.name.trim();
        if (player.initials.trim()) {
            displayName += " (" + player.initials.trim() + ")";
        }
        if (displayName) {
            dropdownOptions[id] = displayName;
        }
    });

    // Create the dropdown.
    // - ID: "playerDropdown"
    // - Default summary text: "Select Player"
    // - We pass `dropdownOptions` for the list
    // - No defaultValue => user must manually select
    // - Sort options by name
    // - Callback => once a user picks a player, we refresh personal scoreboard
    var dropDownElement = await window.createDropDownElement(
        "playerDropdown",
        "Select Player",
        dropdownOptions,
        null,    // no default value
        true,    // sort the options
        function (value, text) {
            console.log("Player selected => " + value + ": " + text);
            // Now that a player is selected, load personal scoreboard
            window.updatePersonalArticles();
        }
    );

    // Clear container, place the new dropdown
    playerDropdownContainer.innerHTML = '';
    playerDropdownContainer.appendChild(dropDownElement);
};

/*
 * Auto-Refresh: only refresh the active board every 60 seconds.
 */
var refreshFunctions = {
    "leader-board": window.updateLeaderboardArticles,
    "tournament-board": window.updateTournamentArticles,
    "personal-board": window.updatePersonalArticles
};

window.startAutoRefreshForTab = function (tabId) {
    if (window.currentRefreshIntervalId) {
        clearInterval(window.currentRefreshIntervalId);
        window.currentRefreshIntervalId = null;
    }

    var containerId = "";
    if (tabId === "leader-board") containerId = "leaderboardArticles";
    else if (tabId === "tournament-board") containerId = "tournamentArticles";
    else if (tabId === "personal-board") containerId = "personalArticles";

    var container = document.getElementById(containerId);
    if (!container) return;

    var refreshFn = refreshFunctions[tabId];
    window.currentRefreshIntervalId = setInterval(function () {
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
 * showTab: Switch between tabs, refresh data, start auto-refresh on new tab.
 */
window.showTab = function (tabId) {
    // Hide all tab-content sections
    var tabs = document.querySelectorAll('.tab-content');
    tabs.forEach(function (tab) {
        tab.classList.remove('active');
    });

    // Show the selected tab
    var selectedTab = document.getElementById(tabId);
    if (selectedTab) {
        selectedTab.classList.add('active');
    }

    // Update button highlight
    var buttons = document.querySelectorAll('#score-board-nav button');
    buttons.forEach(function (button) {
        button.classList.remove('contrast');
    });

    var activeButton = document.querySelector('button[onclick="window.showTab(\'' + tabId + '\')"]');
    if (activeButton) {
        activeButton.classList.add('contrast');
    }

    // Immediately fetch new data (but personal board will only show data if a player is selected)
    if (tabId === "leader-board") {
        window.updateLeaderboardArticles();
    } else if (tabId === "tournament-board") {
        window.updateTournamentArticles();
    } else if (tabId === "personal-board") {
        window.updatePersonalArticles();
    }

    // Start auto-refresh
    window.startAutoRefreshForTab(tabId);
};

/*
 * cleanupRefreshes: in case we want to clear intervals on unload, for example
 */
window.cleanupRefreshes = function () {
    if (window.currentRefreshIntervalId) {
        clearInterval(window.currentRefreshIntervalId);
        window.currentRefreshIntervalId = null;
    }
};

/*
 * pollForElements: “poor man’s” DOM-ready. Once the scoreboard container
 * and nav are in the DOM, load the default leaderboard and THEN load players.
 * We do NOT auto-update personal board until user selects from dropdown.
 */
(function pollForElements() {
    if (document.getElementById("leaderboardArticles") && document.getElementById("score-board-nav")) {
        window.updateLeaderboardArticles();
        window.startAutoRefreshForTab("leader-board");

        // Load the players for the personal board dropdown
        fetch('/api/players')
            .then(function (response) {
                if (!response.ok) throw new Error("Network response was not ok: " + response.statusText);
                return response.json();
            })
            .then(function (data) {
                window.loadPlayers(data);
            })
            .catch(function (error) {
                console.error("Error fetching players:", error);
            });
    } else {
        setTimeout(pollForElements, 100);
    }
})();

// get claimable scores
window.getClaimableScores = async function () {
    const response = await window.smartFetch('/api/scores/claimable', null, false)
    const data = await response.json()

    console.log(data)
    // eample data with 2 games, one with 2 players and one with 1 player
    // [
    //  [['', 1123980]]
    //  [['MSM',11264], ['',9307882]]
    // ]

    const claimableScores = document.getElementById('claimable-scores')

    // if the length of the data is 0, hide the claimable scores
    if (data.length === 0) {
        claimableScores.classList.add('hide')
        return
    }

    // clear the claimable scores
    claimableScores.innerHTML = ''

    // add header
    const header = document.createElement('h4')
    header.innerText = 'Claimable Scores'
    claimableScores.appendChild(header)

    const playerNumberHeader = document.createElement('article')
    playerNumberHeader.classList.add('game')
    playerNumberHeader.classList.add('claim-header-row')
    playerNumberHeader.innerHTML = '<div>Player 1</div><div>Player 2</div><div>Player 3</div><div>Player 4</div>'
    claimableScores.appendChild(playerNumberHeader)

    // for element in data create a new "game" element
    data.forEach((element) => {
        const game = document.createElement('article')
        game.classList.add('game')

        // add a game record for each player in the game
        element.forEach((player) => {
            // make a play element
            const playDiv = document.createElement('div')
            playDiv.classList.add('play')

            // make a player and a score div
            const initialsDiv = document.createElement('div')
            const scoreDiv = document.createElement('div')

            // add the player and score divs to the game div
            playDiv.appendChild(initialsDiv)
            playDiv.appendChild(scoreDiv)

            // add the play div to the game div
            game.appendChild(playDiv)

            // add the score to the score div
            scoreDiv.innerText = player[1]

            // if the initials are present, use them, otherwise replace with a "claim" button
            if (player[0] === '') {
                const claimButton = document.createElement('button')
                claimButton.innerText = 'Claim'
                claimButton.classList.add('claim-button')
                initialsDiv.appendChild(claimButton)
            } else {
                initialsDiv.innerText = player[0]
            }
        })
        claimableScores.appendChild(game)
    })

    // unhides the claimable scores
    claimableScores.classList.remove('hide')
};

window.getClaimableScores();
