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

    fetch('/api/player/scores', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: player_id })
    })
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
                claimButton.addEventListener('click', async () => {
                    const modal = document.getElementById('score-claim-modal')

                    // set modal score
                    const modalScore = document.getElementById('score-to-claim')
                    modalScore.innerText = player[1]

                    // set player number
                    const playerNumber = document.getElementById('player-number')
                    playerNumber.innerText = element.indexOf(player) + 1

                    // replace the submit button with a new one
                    const submit = document.getElementById('submit-claim-btn')
                    const newSubmit = submit.cloneNode(true)
                    submit.parentNode.replaceChild(newSubmit, submit)
                    newSubmit.id = 'submit-claim-btn'

                    // make submit callback
                    newSubmit.addEventListener('click', async () => {
                        const initials = document.getElementById('initials-input').value
                        const response = await window.smartFetch(
                            '/api/scores/claim',
                            { score: player[1], initials: initials, player_index: element.indexOf(player)},
                            false
                        )

                        // get response status
                        const status = await response.status
                        if (status === 200) {
                            window.getClaimableScores()
                        }
                        modal.close()
                    })

                    // show modal
                    modal.showModal();
                })

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

window.getGameStatus = async function () {
    const response = await window.smartFetch('/api/game/status', null, false);
    const data = await response.json();

    const gameStatus = document.getElementById('game-status');

    // if the game is not in progress, hide the game status
    if (data.GameActive !== true) {
        gameStatus.classList.add('hide');
        return;
    }

    // If the game is active, show the container
    gameStatus.classList.remove('hide');

    // Initialize score history if not exists
    if (!window.scoreHistory) {
        window.scoreHistory = {
            1: { changes: [], lastScore: 0, initialized: false },
            2: { changes: [], lastScore: 0, initialized: false },
            3: { changes: [], lastScore: 0, initialized: false },
            4: { changes: [], lastScore: 0, initialized: false }
        };
    }

    // Populate the players with their scores
    const players = document.getElementById('live-players');

    for (const tag of players.children) {
        // get the player id
        const playerId = tag.id.split('-')[2];

        // if the player is not in the game or has a score of 0, hide the tag
        const scoreElement = document.getElementById(`live-player-${playerId}-score`);
        const newScore = data.Scores[playerId - 1];

        if (newScore === undefined || newScore === 0) {
            tag.classList.add('hide');
            continue;
        } else {
            tag.classList.remove('hide');

            // Make sure .css-score-anim is on this score element:
            scoreElement.classList.add('css-score-anim');

            // Track if this is the first score we're seeing for this player
            const playerHistory = window.scoreHistory[playerId];
            const isInitialScore = !playerHistory.initialized;

            // Get the old score from the current CSS variable (fallback to 0 if not set)
            const style = window.getComputedStyle(scoreElement);
            const oldScore = parseInt(style.getPropertyValue('--num') || '0', 10);

            // Mark this player as initialized
            playerHistory.initialized = true;

            // Calculate score change and update history
            if (oldScore > 0 && newScore !== oldScore) {
                const change = newScore - oldScore;

                // Only track positive changes for average calculation
                if (change > 0) {
                    playerHistory.changes.push(change);

                    // Keep only last 10 changes to calculate rolling average
                    if (playerHistory.changes.length > 10) {
                        playerHistory.changes.shift();
                    }
                }
            }

            // If newScore is different from oldScore, update the CSS variable to animate
            if (newScore !== oldScore) {
                scoreElement.style.setProperty('--num', newScore);

                // Only handle positive score changes for animations
                // AND only if this isn't the initial score load
                if (newScore > oldScore && !isInitialScore) {
                    const change = newScore - oldScore;

                    // Calculate average change for this player
                    const avgChange = playerHistory.changes.length > 0
                        ? playerHistory.changes.reduce((sum, val) => sum + val, 0) / playerHistory.changes.length
                        : change; // If no history, use current change as average

                    // Calculate how significant this change is compared to average
                    const significance = change / (avgChange || 1); // Avoid division by zero

                    // Remove any existing animation classes
                    scoreElement.classList.remove('small-jump', 'medium-jump', 'big-jump', 'epic-jump');

                    // Determine animation type and scale based on significance
                    let jumpClass = 'small-jump';
                    let scale = 1.5;
                    let duration = 800;

                    if (significance >= 4) {
                        // Epic change (4+ times average)
                        jumpClass = 'epic-jump';
                        scale = 3.0;
                        duration = 2500;
                    } else if (significance >= 2) {
                        // Large change (2-4 times average)
                        jumpClass = 'big-jump';
                        scale = 2.5;
                        duration = 1500;
                    } else if (significance >= 1) {
                        // Medium change (average to 2x average)
                        jumpClass = 'medium-jump';
                        scale = 1.8;
                        duration = 1000;
                    } else {
                        // Below average change
                        jumpClass = 'small-jump';
                        scale = 1.5;
                        duration = 800;
                    }

                    // Set animation properties
                    scoreElement.style.setProperty('--jumpScale', scale.toFixed(2));
                    scoreElement.style.setProperty('--animDuration', `${duration}ms`);

                    // Apply the animation class
                    scoreElement.classList.add(jumpClass);

                    // Remove animation class after it completes
                    setTimeout(() => {
                        scoreElement.classList.remove(jumpClass);
                    }, duration);

                    console.log(`Player ${playerId}: Change: ${change}, Avg: ${avgChange.toFixed(0)}, Significance: ${significance.toFixed(2)}`);
                }
            }

            // Update last score
            playerHistory.lastScore = newScore;
        }
    }

    // Ball in play
    const ballInPlay = document.getElementById('live-ball-in-play');
    if (data.BallInPlay > 0) {
        ballInPlay.innerText = `Ball in Play: ${data.BallInPlay}`;
        ballInPlay.classList.remove('hide');
    } else {
        ballInPlay.classList.add('hide');
    }
};

// Initial call
window.getGameStatus();

// call getGameStatus function every 0.5 seconds
setInterval(window.getGameStatus, 1000);
