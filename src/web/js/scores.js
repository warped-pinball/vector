/* scores.js */

// Global variable for the current auto-refresh interval
window.currentRefreshIntervalId = null;

/*
 * Function: renderHeaderRow
 * Renders a header row (with column labels) into the specified container.
 * The extra class (colClass) determines the grid layout (e.g. "four-col" or "three-col").
 */
window.renderHeaderRow = function(containerId, columns, colClass) {
  var container = document.getElementById(containerId);
  if (!container) return;
  var headerArticle = document.createElement('article');
  headerArticle.classList.add('header-row', colClass);
  // Render one cell per column
  columns.forEach(function(col) {
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
 * For the "player" column, it combines "initials" and "full_name" (if available).
 * If prefixRank is true, a '#' is added before the rank value.
 */
window.renderDataRow = function(item, columns, colClass, prefixRank) {
  var articleRow = document.createElement('article');
  articleRow.classList.add('score-row', colClass);
  columns.forEach(function(col) {
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
      value = item[col.key] !== undefined ? item[col.key] : "";
      if (col.key === "rank" && prefixRank) {
        value = "#" + value;
      }
    }
    cellDiv.innerText = value;
    articleRow.appendChild(cellDiv);
  });
  return articleRow;
};

/*
 * Function: renderFullArticleList
 * Clears the container and renders a header row followed by all data rows.
 */
window.renderFullArticleList = function(containerId, data, columns, colClass, prefixRank) {
  var container = document.getElementById(containerId);
  if (!container) return;
  container.innerHTML = ''; // Clear previous content.
  window.renderHeaderRow(containerId, columns, colClass);
  data.forEach(function(item) {
    var row = window.renderDataRow(item, columns, colClass, prefixRank);
    container.appendChild(row);
  });
};

/*
 * Function: updateLeaderboardArticles
 * Fetches leaderboard data from the API and renders it using a 4-column board:
 * Columns: Rank, Score, Player, Date.
 */
window.updateLeaderboardArticles = function() {
  var columns = [
    { header: "Rank", key: "rank" },
    { header: "Score", key: "score" },
    { header: "Player", key: "player" },
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
      // Use "four-col" for 4-column boards; prefix rank with '#'
      window.renderFullArticleList("leaderboardArticles", data, columns, "four-col", true);
    })
    .catch(function(error) {
      console.error("Error fetching leaderboard data:", error);
    });
};

/*
 * Function: updateTournamentArticles
 * Fetches tournament data from the API and renders it as a 4-column board:
 * Columns: Game #, Rank, Score, Initials.
 */
window.updateTournamentArticles = function() {
  var columns = [
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
      window.renderFullArticleList("tournamentArticles", data, columns, "four-col", true);
    })
    .catch(function(error) {
      console.error("Error fetching tournament data:", error);
    });
};

/*
 * Function: updatePersonalArticles
 * Fetches personal score data for the selected player and renders it as a 3-column board:
 * Columns: Rank, Score, Date. (Player column is omitted.)
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
  var columns = [
    { header: "Rank", key: "rank" },
    { header: "Score", key: "score" },
    { header: "Date", key: "date" }
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
      // Use "three-col" for personal scores; prefix rank with '#'
      window.renderFullArticleList("personalArticles", data, columns, "three-col", true);
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
      return player.name.trim() !== '' || player.initials.trim() !== '';
    })
    .sort(function(a, b) {
      return a[1].name.localeCompare(b[1].name);
    });
  var playersSelect = document.getElementById('players');
  if (!playersSelect) return;
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
  if (!container) return;
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
 * Switches visible tabs, updates active button styling, refreshes data immediately,
 * and starts auto-refresh for the visible tab.
 */
window.showTab = function(tabId) {
  var tabs = document.querySelectorAll('.tab-content');
  tabs.forEach(function(tab) {
    tab.classList.remove('active');
  });
  var selectedTab = document.getElementById(tabId);
  if (selectedTab) {
    selectedTab.classList.add('active');
  }
  var buttons = document.querySelectorAll('#score-board-nav button');
  buttons.forEach(function(button) {
    button.classList.remove('contrast');
  });
  var activeButton = document.querySelector('button[onclick="window.showTab(\'' + tabId + '\')"]');
  if (activeButton) {
    activeButton.classList.add('contrast');
  }
  if (tabId === "leader-board") {
    window.updateLeaderboardArticles();
  } else if (tabId === "tournament-board") {
    window.updateTournamentArticles();
  } else if (tabId === "personal-board") {
    window.updatePersonalArticles();
  }
  window.startAutoRefreshForTab(tabId);
};

window.cleanupRefreshes = function() {
  if (window.currentRefreshIntervalId) {
    clearInterval(window.currentRefreshIntervalId);
    window.currentRefreshIntervalId = null;
  }
};

/*
 * Poll for elements (since DOM load events aren’t reliably detected).
 * Once the main container and navigation are available, load the default leaderboard,
 * start auto-refresh, and load the player list.
 */
(function pollForElements() {
  if (document.getElementById("leaderboardArticles") && document.getElementById("score-board-nav")) {
    window.updateLeaderboardArticles();
    window.startAutoRefreshForTab("leader-board");
    fetch('/api/players')
      .then(function(response) { return response.json(); })
      .then(function(data) { window.loadPlayers(data); })
      .catch(function(error) { console.error("Error fetching players:", error); });
  } else {
    setTimeout(pollForElements, 100);
  }
})();
