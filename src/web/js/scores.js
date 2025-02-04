/* scores.js */

// Global variables for Grid.js instances and auto-refresh interval
window.leaderboardGrid = null;
window.tournamentGrid = null;
window.personalGrid = null;
window.currentRefreshIntervalId = null;

/*
 * Function: updateLeaderboard
 * Fetches leaderboard data and renders/updates a Grid.js table.
 * Columns: Rank, Score, Player, Date.
 */
window.updateLeaderboard = function() {
  fetch('/api/leaders')
    .then(function(response) {
      if (!response.ok) throw new Error(response.statusText);
      return response.json();
    })
    .then(function(data) {
      localStorage.setItem('/api/leaders', JSON.stringify(data));
      // Process data to ensure proper values (and combine initials/full_name)
      const processedData = data.map(row => ({
        rank: row.rank,
        score: row.score,
        player: row.initials + (row.full_name ? " (" + row.full_name + ")" : ""),
        date: row.date
      }));

      if (window.leaderboardGrid) {
        window.leaderboardGrid.updateConfig({ data: processedData }).forceRender();
      } else {
        window.leaderboardGrid = new gridjs.Grid({
          columns: [
            {
              name: "Rank",
              data: (row) => "#" + row.rank,
              formatter: (cell) => gridjs.html(`<div data-label="Rank">${cell}</div>`),
              sort: true
            },
            {
              name: "Score",
              data: (row) => row.score || "",
              formatter: (cell) => gridjs.html(`<div data-label="Score">${cell}</div>`),
              sort: true
            },
            {
              name: "Player",
              data: (row) => row.player,
              formatter: (cell) => gridjs.html(`<div data-label="Player">${cell}</div>`),
              sort: true
            },
            {
              name: "Date",
              data: (row) => row.date || "",
              formatter: (cell) => gridjs.html(`<div data-label="Date">${cell}</div>`),
              sort: true
            }
          ],
          data: processedData,
          sort: true,
          pagination: { limit: 10 },
          style: { table: { width: "100%" } }
        }).render(document.getElementById("leaderboardArticles"));
      }
    })
    .catch(function(error) {
      console.error("Error fetching leaderboard data:", error);
    });
};

/*
 * Function: updateTournament
 * Fetches tournament data and renders/updates a Grid.js table.
 * Columns: Game #, Rank, Score, Initials.
 */
window.updateTournament = function() {
  fetch('/api/tournament')
    .then(function(response) {
      if (!response.ok) throw new Error(response.statusText);
      return response.json();
    })
    .then(function(data) {
      localStorage.setItem('/api/tournament', JSON.stringify(data));
      const processedData = data.map(row => ({
        game: row.game,
        rank: row.rank,
        score: row.score,
        initials: row.initials
      }));

      if (window.tournamentGrid) {
        window.tournamentGrid.updateConfig({ data: processedData }).forceRender();
      } else {
        window.tournamentGrid = new gridjs.Grid({
          columns: [
            {
              name: "Game #",
              data: (row) => row.game || "",
              formatter: (cell) => gridjs.html(`<div data-label="Game #">${cell}</div>`),
              sort: true
            },
            {
              name: "Rank",
              data: (row) => "#" + row.rank,
              formatter: (cell) => gridjs.html(`<div data-label="Rank">${cell}</div>`),
              sort: true
            },
            {
              name: "Score",
              data: (row) => row.score || "",
              formatter: (cell) => gridjs.html(`<div data-label="Score">${cell}</div>`),
              sort: true
            },
            {
              name: "Initials",
              data: (row) => row.initials || "",
              formatter: (cell) => gridjs.html(`<div data-label="Initials">${cell}</div>`),
              sort: true
            }
          ],
          data: processedData,
          sort: true,
          pagination: { limit: 10 },
          style: { table: { width: "100%" } }
        }).render(document.getElementById("tournamentArticles"));
      }
    })
    .catch(function(error) {
      console.error("Error fetching tournament data:", error);
    });
};

/*
 * Function: updatePersonal
 * Fetches personal scores for the selected player and renders/updates a Grid.js table.
 * Columns: Rank, Score, Date. (Player column is omitted.)
 */
window.updatePersonal = function() {
  var playerSelect = document.getElementById("players");
  if (!playerSelect) return;
  var player_id = playerSelect.value;
  if (!player_id) return;
  fetch('/api/player/scores?id=' + player_id)
    .then(function(response) {
      if (!response.ok) throw new Error(response.statusText);
      return response.json();
    })
    .then(function(data) {
      localStorage.setItem('/api/player/scores?id=' + player_id, JSON.stringify(data));
      const processedData = data.map(row => ({
        rank: row.rank,
        score: row.score,
        date: row.date
      }));

      if (window.personalGrid) {
        window.personalGrid.updateConfig({ data: processedData }).forceRender();
      } else {
        window.personalGrid = new gridjs.Grid({
          columns: [
            {
              name: "Rank",
              data: (row) => "#" + row.rank,
              formatter: (cell) => gridjs.html(`<div data-label="Rank">${cell}</div>`),
              sort: true
            },
            {
              name: "Score",
              data: (row) => row.score || "",
              formatter: (cell) => gridjs.html(`<div data-label="Score">${cell}</div>`),
              sort: true
            },
            {
              name: "Date",
              data: (row) => row.date || "",
              formatter: (cell) => gridjs.html(`<div data-label="Date">${cell}</div>`),
              sort: true
            }
          ],
          data: processedData,
          sort: true,
          pagination: { limit: 10 },
          className: { table: "personal-grid" },
          style: { table: { width: "100%" } }
        }).render(document.getElementById("personalArticles"));
      }
    })
    .catch(function(error) {
      console.error("Error fetching personal scores:", error);
    });
};

/*
 * Function: loadPlayers
 * Loads player data into the dropdown and sets up a change listener.
 */
window.loadPlayers = function(data) {
  var players = Object.entries(data)
    .filter(function(entry) {
      var player = entry[1];
      return player.name.trim() !== "" || player.initials.trim() !== "";
    })
    .sort(function(a, b) {
      return a[1].name.localeCompare(b[1].name);
    });
  var playersSelect = document.getElementById("players");
  if (!playersSelect) return;
  playersSelect.innerHTML = "";
  players.forEach(function(entry) {
    var id = entry[0],
      player = entry[1];
    var option = document.createElement("option");
    option.value = id;
    option.text = player.name + (player.initials ? " (" + player.initials + ")" : "");
    playersSelect.appendChild(option);
  });
  if (players.length > 0) {
    playersSelect.value = players[0][0];
    window.updatePersonal();
  }
  playersSelect.addEventListener("change", function () {
    window.updatePersonal();
  });
};

/*
 * Auto-Refresh: Only the visible board auto-refreshes every 60 seconds.
 */
var refreshFunctions = {
  "leader-board": window.updateLeaderboard,
  "tournament-board": window.updateTournament,
  "personal-board": window.updatePersonal
};

window.startAutoRefreshForTab = function (tabId) {
  if (window.currentRefreshIntervalId) {
    clearInterval(window.currentRefreshIntervalId);
    window.currentRefreshIntervalId = null;
  }
  var refreshFn = refreshFunctions[tabId];
  window.currentRefreshIntervalId = setInterval(function () {
    refreshFn();
  }, 60000);
};

/*
 * Function: showTab
 * Switches visible tabs, updates active button styling, refreshes data immediately,
 * and starts auto-refresh for the visible board.
 */
window.showTab = function (tabId) {
  document.querySelectorAll(".tab-content").forEach(function (tab) {
    tab.classList.remove("active");
  });
  var selectedTab = document.getElementById(tabId);
  if (selectedTab) selectedTab.classList.add("active");

  document.querySelectorAll("#score-board-nav button").forEach(function (button) {
    button.classList.remove("contrast");
  });
  var activeButton = document.querySelector('button[onclick="window.showTab(\'' + tabId + '\')"]');
  if (activeButton) activeButton.classList.add("contrast");

  if (tabId === "leader-board") {
    window.updateLeaderboard();
  } else if (tabId === "tournament-board") {
    window.updateTournament();
  } else if (tabId === "personal-board") {
    window.updatePersonal();
  }
  window.startAutoRefreshForTab(tabId);
};

window.cleanupRefreshes = function () {
  if (window.currentRefreshIntervalId) {
    clearInterval(window.currentRefreshIntervalId);
    window.currentRefreshIntervalId = null;
  }
};

/*
 * Poll for essential elements (since DOM load events aren’t reliably detected).
 * Once available, load the default leaderboard, start auto-refresh,
 * and load the player list.
 */
(function pollForElements() {
  if (document.getElementById("leaderboardArticles") && document.getElementById("score-board-nav")) {
    window.updateLeaderboard();
    window.startAutoRefreshForTab("leader-board");
    fetch("/api/players")
      .then(function (response) { return response.json(); })
      .then(function (data) { window.loadPlayers(data); })
      .catch(function (error) { console.error("Error fetching players:", error); });
  } else {
    setTimeout(pollForElements, 100);
  }
})();
