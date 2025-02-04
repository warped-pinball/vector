/* scores.js */

// Expose everything on window so inline HTML calls like window.showTab(...) work
window.leaderboardList = null;
window.tournamentList = null;
window.personalList = null;
window.currentRefreshIntervalId = null;

/*
 * Helper: format player (combine initials & fullName)
 */
window.formatPlayer = function(initials, fullName) {
  if (fullName && fullName.trim() !== "") {
    return initials + " (" + fullName + ")";
  }
  return initials;
};

/*
 * Create our List.js instances for each scoreboard.
 * We must ensure #leaderboardList, #tournamentList, #personalList exist
 * (and that List is loaded) before calling new List(...).
 */
window.initLists = function() {
  // LEADERBOARD
  if (!window.leaderboardList) {
    const leaderboardOptions = {
      valueNames: ['rank', 'score', 'player', 'date'],
      /* The item template is used for each row.
         We'll use article.four-col to match our CSS. */
      item: `
        <article class="item four-col">
          <div class="rank"></div>
          <div class="score"></div>
          <div class="player"></div>
          <div class="date"></div>
        </article>`
    };
    window.leaderboardList = new List('leaderboardList', leaderboardOptions);
  }

  // TOURNAMENT
  if (!window.tournamentList) {
    const tournamentOptions = {
      valueNames: ['game', 'rank', 'score', 'initials'],
      item: `
        <article class="item four-col">
          <div class="game"></div>
          <div class="rank"></div>
          <div class="score"></div>
          <div class="initials"></div>
        </article>`
    };
    window.tournamentList = new List('tournamentList', tournamentOptions);
  }

  // PERSONAL
  if (!window.personalList) {
    const personalOptions = {
      valueNames: ['rank', 'score', 'date'],
      item: `
        <article class="item three-col">
          <div class="rank"></div>
          <div class="score"></div>
          <div class="date"></div>
        </article>`
    };
    window.personalList = new List('personalList', personalOptions);
  }
};

/*
 * fetch + load data for the Leaderboard
 */
window.updateLeaderboardArticles = function() {
  fetch('/api/leaders')
    .then(function(res) {
      if (!res.ok) { throw new Error("Network error: " + res.statusText); }
      return res.json();
    })
    .then(function(data) {
      /*
       * data example: [
       *   { rank: 1, score: 50000, initials: "ABC", full_name: "Alice Bob", date: "2025-01-01" },
       *   ...
       * ]
       */
      const items = data.map(function(item) {
        return {
          rank: "#" + item.rank,
          score: item.score,
          player: window.formatPlayer(item.initials, item.full_name),
          date: item.date
        };
      });
      // If we haven't created leaderboardList yet, do so now
      if (!window.leaderboardList) {
        window.initLists();
      }
      window.leaderboardList.clear();
      window.leaderboardList.add(items);
      window.leaderboardList.sort('score', { order: 'desc' });
    })
    .catch(function(err) {
      console.error("Error updating leaderboard:", err);
    });
};

/*
 * fetch + load data for the Tournament
 */
window.updateTournamentArticles = function() {
  fetch('/api/tournament')
    .then(function(res) {
      if (!res.ok) { throw new Error("Network error: " + res.statusText); }
      return res.json();
    })
    .then(function(data) {
      // e.g. [{ game: 1, rank: 2, score: 23456, initials: "XYZ" }, ...]
      const items = data.map(function(item) {
        return {
          game: item.game,
          rank: "#" + item.rank,
          score: item.score,
          initials: item.initials
        };
      });
      if (!window.tournamentList) {
        window.initLists();
      }
      window.tournamentList.clear();
      window.tournamentList.add(items);
      window.tournamentList.sort('score', { order: 'desc' });
    })
    .catch(function(err) {
      console.error("Error updating tournament:", err);
    });
};

/*
 * fetch + load data for the Personal scoreboard
 */
window.updatePersonalArticles = function() {
  const playerSelect = document.getElementById('players');
  if (!playerSelect) return;
  const player_id = playerSelect.value;
  if (!player_id) return;

  fetch('/api/player/scores?id=' + player_id)
    .then(function(res) {
      if (!res.ok) { throw new Error("Network error: " + res.statusText); }
      return res.json();
    })
    .then(function(data) {
      // e.g. [{ rank: 1, score: 12345, date: "2025-02-04" }, ...]
      const items = data.map(function(item) {
        return {
          rank: "#" + item.rank,
          score: item.score,
          date: item.date
        };
      });
      if (!window.personalList) {
        window.initLists();
      }
      window.personalList.clear();
      window.personalList.add(items);
      window.personalList.sort('score', { order: 'desc' });
    })
    .catch(function(err) {
      console.error("Error updating personal scores:", err);
    });
};

/*
 * loadPlayers
 */
window.loadPlayers = function(data) {
  const playersSelect = document.getElementById('players');
  if (!playersSelect) return;
  playersSelect.innerHTML = '';

  Object.entries(data)
    .sort(function(a, b) { return a[1].name.localeCompare(b[1].name); })
    .forEach(function(entry) {
      const [id, playerObj] = entry;
      const option = document.createElement('option');
      option.value = id;
      option.text = playerObj.name + (playerObj.initials ? " (" + playerObj.initials + ")" : "");
      playersSelect.appendChild(option);
    });

  if (playersSelect.options.length > 0) {
    playersSelect.value = playersSelect.options[0].value;
    window.updatePersonalArticles();
  }

  playersSelect.addEventListener('change', function() {
    window.updatePersonalArticles();
  });
};

/*
 * Only refresh the visible board every 60s
 */
window.refreshFunctions = {
  "leader-board": window.updateLeaderboardArticles,
  "tournament-board": window.updateTournamentArticles,
  "personal-board": window.updatePersonalArticles
};

window.startAutoRefreshForTab = function(tabId) {
  if (window.currentRefreshIntervalId) {
    clearInterval(window.currentRefreshIntervalId);
    window.currentRefreshIntervalId = null;
  }
  const fn = window.refreshFunctions[tabId];
  if (fn) {
    window.currentRefreshIntervalId = setInterval(fn, 60000);
  }
};

/*
 * showTab: hide other tabs, show the chosen tab, update data, start auto refresh
 */
window.showTab = function(tabId) {
  const tabs = document.querySelectorAll('.tab-content');
  tabs.forEach(function(tab) {
    tab.classList.remove('active');
  });
  const selectedTab = document.getElementById(tabId);
  if (selectedTab) {
    selectedTab.classList.add('active');
  }
  const buttons = document.querySelectorAll('#score-board-nav button');
  buttons.forEach(function(b) { b.classList.remove('contrast'); });
  const activeButton = document.querySelector('button[onclick="window.showTab(\'' + tabId + '\')"]');
  if (activeButton) {
    activeButton.classList.add('contrast');
  }

  // Trigger immediate update
  if (tabId === 'leader-board') {
    window.updateLeaderboardArticles();
  } else if (tabId === 'tournament-board') {
    window.updateTournamentArticles();
  } else if (tabId === 'personal-board') {
    window.updatePersonalArticles();
  }
  // Start auto-refresh
  window.startAutoRefreshForTab(tabId);
};

window.cleanupRefreshes = function() {
  if (window.currentRefreshIntervalId) {
    clearInterval(window.currentRefreshIntervalId);
    window.currentRefreshIntervalId = null;
  }
};

/*
 * Poll to ensure:
 *   1) #leaderboardList, #tournamentList, #personalList exist
 *   2) #score-board-nav exists
 *   3) List is loaded (typeof List !== "undefined")
 * Then run initLists() & load default data.
 */
(function pollForElements() {
  if (
    document.getElementById("leaderboardList") &&
    document.getElementById("tournamentList") &&
    document.getElementById("personalList") &&
    document.getElementById("score-board-nav") &&
    typeof List !== "undefined"
  ) {
    // We have all the necessary elements & list.js is loaded
    // Initialize the lists:
    window.initLists();

    // Default to Leaderboard
    window.updateLeaderboardArticles();
    window.startAutoRefreshForTab("leader-board");

    // Load players for the personal scoreboard
    fetch('/api/players')
      .then(res => res.json())
      .then(data => window.loadPlayers(data))
      .catch(err => console.error("Error fetching players:", err));

  } else {
    setTimeout(pollForElements, 200); // check again in 200ms
  }
})();
