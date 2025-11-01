/* scores.js */

// Global variable for the current auto-refresh interval
window.currentRefreshIntervalId = null;

// Format numeric scores with commas for readability
window.formatScore = function (score) {
  var num = parseInt(score, 10);
  if (isNaN(num)) return score;
  return num.toLocaleString();
};

/*
 * Function: renderHeaderRow
 * Renders a header row (with column labels) into the specified container.
 */
window.renderHeaderRow = function (containerId, columns, colClass) {
  var container = document.getElementById(containerId);
  if (!container) return;
  var headerArticle = document.createElement("article");
  headerArticle.classList.add("header-row", colClass);

  // Render one cell per column
  columns.forEach(function (col) {
    var cellDiv = document.createElement("div");
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
  var articleRow = document.createElement("article");
  articleRow.classList.add("score-row", colClass);

  columns.forEach(function (col) {
    var cellDiv = document.createElement("div");
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
    } else if (col.key === "score") {
      value = window.formatScore(item[col.key]);
    } else {
      // For the rank column, we do not prepend "#"
      value = item[col.key] !== undefined ? item[col.key] : "";
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
  container.innerHTML = ""; // Clear previous content

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
  //If we're in delete mode, don't refresh the board!!!!
  if (window.scoreDeleteMode) {
    return;
  }

  var columns = [
    { header: "#", key: "rank" },
    { header: "Score", key: "score" },
    { header: "Player", key: "player" },
    { header: "Ago", key: "ago" },
    { header: "Date", key: "date" },
  ];

  var container = document.getElementById("leaderboardArticles");
  if (!container) {
    if (window.currentRefreshIntervalId) {
      clearInterval(window.currentRefreshIntervalId);
      window.currentRefreshIntervalId = null;
    }
    return;
  }

  fetch("/api/leaders")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Network response was not ok: " + response.statusText);
      }
      return response.json();
    })
    .then(function (data) {
      localStorage.setItem("/api/leaders", JSON.stringify(data));
      window.renderFullArticleList(
        "leaderboardArticles",
        data,
        columns,
        "five-col",
      );
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
    { header: "Score", key: "score" },
  ];

  var container = document.getElementById("tournamentArticles");
  if (!container) {
    if (window.currentRefreshIntervalId) {
      clearInterval(window.currentRefreshIntervalId);
      window.currentRefreshIntervalId = null;
    }
    return;
  }

  fetch("/api/tournament")
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Network response was not ok: " + response.statusText);
      }
      return response.json();
    })
    .then(function (data) {
      localStorage.setItem("/api/tournament", JSON.stringify(data));
      window.renderFullArticleList(
        "tournamentArticles",
        data,
        columns,
        "four-col-tournament",
      );
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

  // When no player is selected or "all" is chosen show personal bests
  if (!player_id || player_id === "null" || player_id === "all") {
    var columns = [
      { header: "#", key: "rank" },
      { header: "Score", key: "score" },
      { header: "Player", key: "player" },
      { header: "Ago", key: "ago" },
      { header: "Date", key: "date" },
    ];

    fetch("/api/personal/bests")
      .then(function (response) {
        if (!response.ok) {
          throw new Error(
            "Network response was not ok: " + response.statusText,
          );
        }
        return response.json();
      })
      .then(function (data) {
        localStorage.setItem("/api/personal/bests", JSON.stringify(data));
        window.renderFullArticleList(
          "personalArticles",
          data,
          columns,
          "five-col",
        );
      })
      .catch(function (error) {
        console.error("Error fetching personal bests:", error);
      });
    return;
  }

  var columns = [
    { header: "#", key: "rank" },
    { header: "Score", key: "score" },
    { header: "Ago", key: "ago" },
    { header: "Date", key: "date" },
  ];

  fetch("/api/player/scores", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id: player_id }),
  })
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Network response was not ok: " + response.statusText);
      }
      return response.json();
    })
    .then(function (data) {
      localStorage.setItem(
        "/api/player/scores?id=" + player_id,
        JSON.stringify(data),
      );
      window.renderFullArticleList(
        "personalArticles",
        data,
        columns,
        "four-col-personal",
      );
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
  var playerDropdownContainer = document.getElementById(
    "playerDropdownContainer",
  );
  if (!playerDropdownContainer) return;

  // Build a { id: "PlayerName (INI)" } object for the dropdown
  var dropdownOptions = { all: "All Personal Bests" };
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
    "All Personal Bests",
    dropdownOptions,
    null, // no default value
    true, // sort the options
    function (value, text) {
      console.log("Player selected => " + value + ": " + text);
      // Now that a player is selected, load personal scoreboard
      window.updatePersonalArticles();
    },
  );

  // Clear container, place the new dropdown
  playerDropdownContainer.innerHTML = "";
  playerDropdownContainer.appendChild(dropDownElement);

  // Show all personal bests by default
  window.updatePersonalArticles();
};

/*
 * Auto-Refresh: only refresh the active board every 60 seconds.
 */
var refreshFunctions = {
  "leader-board": window.updateLeaderboardArticles,
  "tournament-board": window.updateTournamentArticles,
  "personal-board": window.updatePersonalArticles,
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
  }, 4000);
};

/*
 * showTab: Switch between tabs, refresh data, start auto-refresh on new tab.
 */
window.showTab = function (tabId) {
  // Hide all tab-content sections
  var tabs = document.querySelectorAll(".tab-content");
  tabs.forEach(function (tab) {
    tab.classList.remove("active");
  });

  // Show the selected tab
  var selectedTab = document.getElementById(tabId);
  if (selectedTab) {
    selectedTab.classList.add("active");
  }

  // Update button highlight
  var buttons = document.querySelectorAll("#score-board-nav button");
  buttons.forEach(function (button) {
    button.classList.remove("contrast");
  });

  var activeButton = document.querySelector(
    "button[onclick=\"window.showTab('" + tabId + "')\"]",
  );
  if (activeButton) {
    activeButton.classList.add("contrast");
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
  if (
    document.getElementById("leaderboardArticles") &&
    document.getElementById("score-board-nav")
  ) {
    window.updateLeaderboardArticles();
    window.startAutoRefreshForTab("leader-board");

    // Load the players for the personal board dropdown
    fetch("/api/players")
      .then(function (response) {
        if (!response.ok)
          throw new Error(
            "Network response was not ok: " + response.statusText,
          );
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
  const response = await window.smartFetch(
    "/api/scores/claimable",
    null,
    false,
  );
  const data = await response.json();
  // eample data with 2 games, one with 2 players and one with 1 player
  // [
  //  [['', 1123980]]
  //  [['MSM',11264], ['',9307882]]
  // ]

  const claimableScores = document.getElementById("claimable-scores");

  // if claimable scores is not present, return
  if (!claimableScores) {
    return;
  }

  // if the length of the data is 0, hide the claimable scores
  if (data.length === 0) {
    claimableScores.classList.add("hide");
    return;
  }

  // clear the claimable scores
  claimableScores.innerHTML = "";

  // add header
  const header = document.createElement("h4");
  header.innerText = "Claimable Scores";
  claimableScores.appendChild(header);

  const playerNumberHeader = document.createElement("article");
  playerNumberHeader.classList.add("game");
  playerNumberHeader.classList.add("claim-header-row");
  playerNumberHeader.innerHTML =
    "<div>Player 1</div><div>Player 2</div><div>Player 3</div><div>Player 4</div>";
  claimableScores.appendChild(playerNumberHeader);

  // for element in data create a new "game" element
  data.forEach((element) => {
    const game = document.createElement("article");
    game.classList.add("game");

    // add a game record for each player in the game
    element.forEach((player) => {
      // make a play element
      const playDiv = document.createElement("div");
      playDiv.classList.add("play");

      // make a player and a score div
      const initialsDiv = document.createElement("div");
      const scoreDiv = document.createElement("div");

      // add the player and score divs to the game div
      playDiv.appendChild(initialsDiv);
      playDiv.appendChild(scoreDiv);

      // add the play div to the game div
      game.appendChild(playDiv);

      // add the score to the score div
      scoreDiv.innerText = window.formatScore(player[1]);

      // if the initials are present, use them, otherwise replace with a "claim" button
      if (player[0] === "") {
        const claimButton = document.createElement("button");
        claimButton.addEventListener("click", async () => {
          const modal = document.getElementById("score-claim-modal");

          // set modal score
          const modalScore = document.getElementById("score-to-claim");
          modalScore.innerText = window.formatScore(player[1]);

          // set player number
          const playerNumber = document.getElementById("player-number");
          playerNumber.innerText = element.indexOf(player) + 1;

          // replace the submit button with a new one
          const submit = document.getElementById("submit-claim-btn");
          const newSubmit = submit.cloneNode(true);
          submit.parentNode.replaceChild(newSubmit, submit);
          newSubmit.id = "submit-claim-btn";

          // make submit callback
          newSubmit.addEventListener("click", async () => {
            const initials = document.getElementById("initials-input").value;
            const response = await window.smartFetch(
              "/api/scores/claim",
              {
                score: player[1],
                initials: initials,
                player_index: element.indexOf(player),
              },
              false,
            );

            // get response status
            const status = await response.status;
            if (status === 200) {
              window.getClaimableScores();
            }
            modal.close();
          });

          // show modal
          modal.showModal();
        });

        claimButton.innerText = "Claim";
        claimButton.classList.add("claim-button");
        initialsDiv.appendChild(claimButton);
      } else {
        initialsDiv.innerText = player[0];
      }
    });
    claimableScores.appendChild(game);
  });

  // unhides the claimable scores
  claimableScores.classList.remove("hide");
};

window.getClaimableScores();

/**
 * Game Status and Score Animation Module
 * Manages live game status and animates score changes
 */

// Store score history for animation calculations
window.scoreHistory = {
  1: { changes: [], lastScore: 0, initialized: false },
  2: { changes: [], lastScore: 0, initialized: false },
  3: { changes: [], lastScore: 0, initialized: false },
  4: { changes: [], lastScore: 0, initialized: false },
};

// Firework effect settings
window.fireworkSettings = {
  particleCount: 70,
  minDistance: 50,
  maxDistance: 120,
  minDuration: 1.2,
  maxDuration: 2,
  baseColor: [255, 200, 100], // Warm golden hue
  colorVariance: 40, // Variance in RGB values
  gravity: 30, // Pixels per second squared
  flickerMin: 3, // Min flickers per particle
  flickerMax: 7, // Max flickers per particle
};

/**
 * Fetch current game status from API
 * @returns {Promise<Object>} Game status data
 */
window.fetchGameStatus = async function () {
  const response = await window.smartFetch("/api/game/status", null, false);
  return response.json();
};

/**
 * Calculate animation parameters based on score change
 * @param {number} change - Current score change
 * @param {number} avgChange - Average of recent changes
 * @returns {Object} Animation parameters
 */
window.calculateAnimationParams = function (change, avgChange) {
  // Calculate how significant this change is compared to average
  const significance = change / (avgChange || 1);

  // Default (small changes)
  let params = {
    jumpClass: "small-jump",
    scale: 1.5,
    duration: 800,
  };

  if (significance >= 4) {
    // Epic change (4+ times average)
    params = {
      jumpClass: "epic-jump",
      scale: 3.0,
      duration: 2500,
    };
  } else if (significance >= 2) {
    // Large change (2-4 times average)
    params = {
      jumpClass: "big-jump",
      scale: 2.5,
      duration: 1500,
    };
  } else if (significance >= 1) {
    // Medium change (average to 2x average)
    params = {
      jumpClass: "medium-jump",
      scale: 1.8,
      duration: 1000,
    };
  }

  return params;
};

/**
 * Create firework effect around a score element
 * @param {HTMLElement} scoreElement - DOM element containing the score
 */
window.createFireworkEffect = function (scoreElement) {
  const container = document.getElementById("firework-container");
  if (!container) return;

  const rect = scoreElement.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;

  for (let i = 0; i < window.fireworkSettings.particleCount; i++) {
    const particle = document.createElement("div");
    particle.classList.add("particle");
    container.appendChild(particle);

    const angle = Math.random() * 2 * Math.PI;
    const distance =
      Math.random() *
        (window.fireworkSettings.maxDistance -
          window.fireworkSettings.minDistance) +
      window.fireworkSettings.minDistance;
    const duration =
      Math.random() *
        (window.fireworkSettings.maxDuration -
          window.fireworkSettings.minDuration) +
      window.fireworkSettings.minDuration;

    // Initial velocity components
    const speed = distance / (duration * 0.6);
    const vx = Math.cos(angle) * speed * (0.9 + Math.random() * 0.2);
    const vy = Math.sin(angle) * speed * (0.9 + Math.random() * 0.2);

    // Particle color
    const colorVariance =
      Math.random() * window.fireworkSettings.colorVariance -
      window.fireworkSettings.colorVariance / 2;
    const r = Math.min(
      255,
      window.fireworkSettings.baseColor[0] + colorVariance,
    );
    const g = Math.min(
      255,
      window.fireworkSettings.baseColor[1] + colorVariance,
    );
    const b = Math.min(
      255,
      window.fireworkSettings.baseColor[2] + colorVariance,
    );
    const color = `rgb(${r}, ${g}, ${b})`;

    particle.style.left = `${x}px`;
    particle.style.top = `${y}px`;
    particle.style.backgroundColor = color;
    particle.style.color = color; // For glow

    // Generate random flicker moments
    const flickerCount =
      Math.floor(
        Math.random() *
          (window.fireworkSettings.flickerMax -
            window.fireworkSettings.flickerMin +
            1),
      ) + window.fireworkSettings.flickerMin;
    const flickerTimes = Array(flickerCount)
      .fill()
      .map(() => Math.random());

    // Create keyframes for animation
    const keyframes = [];
    const steps = 30;

    for (let step = 0; step <= steps; step++) {
      const progress = step / steps;
      const time = progress * duration;

      // Physics-based movement with gravity
      const xPos = vx * time;
      const yPos =
        vy * time + 0.5 * window.fireworkSettings.gravity * time * time;

      // Base opacity curve
      let opacity = 1 - Math.pow(progress, 0.8);

      // Check for flicker
      const isNearFlicker = flickerTimes.some(
        (flickerTime) => Math.abs(progress - flickerTime) < 0.05,
      );

      if (isNearFlicker) {
        opacity = Math.min(1.5, opacity + 0.5 + Math.random() * 0.5);
      }

      keyframes.push({
        transform: `translate(${xPos}px, ${yPos}px)`,
        opacity: Math.max(0, opacity),
        boxShadow: `0 0 ${4 + opacity * 3}px ${opacity}px currentColor`,
      });
    }

    particle.animate(keyframes, {
      duration: duration * 1000,
      easing: "cubic-bezier(0.2, 0.8, 0.2, 1)",
      fill: "forwards",
    });

    setTimeout(() => particle.remove(), duration * 1000);
  }
};

/**
 * Apply score animation to an element
 * @param {HTMLElement} element - Score element to animate
 * @param {Object} params - Animation parameters
 */
window.applyScoreAnimation = function (element, params) {
  // Remove any existing animation classes
  element.classList.remove(
    "small-jump",
    "medium-jump",
    "big-jump",
    "epic-jump",
  );

  // Set animation properties
  element.style.setProperty("--jumpScale", params.scale.toFixed(2));
  element.style.setProperty("--animDuration", `${params.duration}ms`);

  // Apply the animation class
  element.classList.add(params.jumpClass);

  // If this is an epic jump, create the firework effect
  if (params.jumpClass === "epic-jump") {
    window.createFireworkEffect(element);
  }

  // Remove animation class after it completes
  setTimeout(() => {
    element.classList.remove(params.jumpClass);
  }, params.duration);
};

/**
 * Process score changes and trigger animations
 * @param {HTMLElement} scoreElement - DOM element containing the score
 * @param {number} playerId - Player ID (1-4)
 * @param {number} newScore - New score to display
 */
window.processScoreChange = function (scoreElement, playerId, newScore) {
  const playerHistory = window.scoreHistory[playerId];
  const isInitialScore = !playerHistory.initialized;

  // Hide score element if score is zero
  if (newScore === 0) {
    scoreElement.classList.add("hide");
    scoreElement.dataset.score = "0";
    return;
  } else {
    scoreElement.classList.remove("hide");
  }

  // Get current displayed score
  const style = window.getComputedStyle(scoreElement);
  const oldScore = parseInt(style.getPropertyValue("--num") || "0", 10);

  // Mark this player as initialized
  playerHistory.initialized = true;

  // Update score and calculate change
  if (oldScore > 0 && newScore !== oldScore) {
    const change = newScore - oldScore;

    // Track positive changes for average calculation
    if (change > 0) {
      playerHistory.changes.push(change);

      // Keep only last 10 changes
      if (playerHistory.changes.length > 10) {
        playerHistory.changes.shift();
      }
    }
  }

  // If score changed, update the CSS variable to animate and display text
  if (newScore !== oldScore) {
    scoreElement.style.setProperty("--num", newScore);
    scoreElement.dataset.score = window.formatScore(newScore);

    // Only animate positive changes after initial load AND initial game setup
    if (
      newScore > oldScore &&
      !isInitialScore &&
      playerHistory.changes.length >= 3
    ) {
      const change = newScore - oldScore;

      // Calculate average change for this player
      const avgChange =
        playerHistory.changes.length > 0
          ? playerHistory.changes.reduce((sum, val) => sum + val, 0) /
            playerHistory.changes.length
          : change;

      // Calculate and apply animation
      const animParams = window.calculateAnimationParams(change, avgChange);
      window.applyScoreAnimation(scoreElement, animParams);

      console.log(
        `Player ${playerId}: Change: ${change}, Avg: ${avgChange.toFixed(
          0,
        )}, Significance: ${(change / avgChange).toFixed(2)}`,
      );
    }
  }

  // Update last score
  playerHistory.lastScore = newScore;
};

/**
 * Update ball in play status
 * @param {Object} data - Game status data
 */
window.updateBallInPlay = function (data) {
  const ballInPlay = document.getElementById("live-ball-in-play");
  if (data.BallInPlay > 0) {
    ballInPlay.innerText = `Ball in Play: ${data.BallInPlay}`;
    ballInPlay.classList.remove("hide");
  } else {
    ballInPlay.classList.add("hide");
  }
};

/**
 * Main function to get and display game status
 */
window.getGameStatus = async function () {
  // Fetch data from API
  const data = await window.fetchGameStatus();
  const gameStatus = document.getElementById("game-status");

  // Exit if no status element
  if (!gameStatus) return;

  // If game not active, hide status and exit
  if (data.GameActive !== true) {
    gameStatus.classList.add("hide");
    // Reset all scores to zero when game is not active
    const players = document.getElementById("live-players");
    if (players) {
      for (let i = 1; i <= 4; i++) {
        const scoreElement = document.getElementById(`live-player-${i}-score`);
        if (scoreElement) {
          scoreElement.style.setProperty("--num", 0);
          scoreElement.dataset.score = "0";
          scoreElement.classList.add("hide");
          window.scoreHistory[i].lastScore = 0;
        }
      }
    }
    return;
  }

  // Game is active, show the container
  gameStatus.classList.remove("hide");

  // Process player scores
  const players = document.getElementById("live-players");
  for (let i = 1; i <= 4; i++) {
    const tag = document.getElementById(`live-player-${i}`);
    const scoreElement = document.getElementById(`live-player-${i}-score`);

    if (!tag || !scoreElement) continue;

    const newScore = data.Scores[i - 1] || 0;

    // Hide players with no score
    if (newScore === 0) {
      // replace score element with empty div with the same id
      const newScoreElement = document.createElement("div");
      newScoreElement.id = scoreElement.id;
      newScoreElement.dataset.score = "0";
      scoreElement.replaceWith(newScoreElement);
      window.scoreHistory[i].lastScore = 0;
      continue;
    }

    // Show player and update score
    tag.classList.remove("hide");
    scoreElement.classList.add("css-score-anim");
    scoreElement.classList.remove("hide"); // Make sure score is visible for non-zero scores
    window.processScoreChange(scoreElement, i, newScore);
  }

  // Update ball in play display
  window.updateBallInPlay(data);
};

window.scoreDeleteMode = false;

window.toggleScoreDelete = function () {
  // switch (tabId) {
  //   case "leader-board":

  //     break;
  //   case "tournament-board":
  //     break;
  //   default:
  //     //Not supported!
  //     return;
  // }

  window.scoreDeleteMode = !window.scoreDeleteMode;

  var rows = document.querySelectorAll(".tab-content.active .score-row .rank");
  var deleteBtn = document.querySelector("#delete-scores-btn");
  if (window.scoreDeleteMode) {
    deleteBtn.classList.add("danger");
    //Switch to checkboxes
    rows.forEach(function (row) {
      var number = row.innerHTML;
      row.innerHTML = '<input type="checkbox" name="' + number + '" />';
    });
  } else {
    deleteBtn.classList.remove("danger");

    var rowsToDelete = [];
    var checkboxes = document.querySelectorAll(
      ".tab-content.active .score-row .rank checkbox",
    );
    checkboxes.forEach(function (checkbox) {
      if (checkbox.checked) {
        rowsToDelete.push(checkbox.name);
      }
    });
    if (rowsToDelete.length > 0) {
      alert(rowsToDelete.join(", "));
    }

    //Switch back to numbers
    rows.forEach(function (row) {
      var checkbox = row.children[0];
      row.innerHTML = checkbox.name;
    });
  }
};

// Initial call
window.getGameStatus();

// Poll for updates
setInterval(window.getGameStatus, 1500);
setInterval(window.getClaimableScores, 4000);
