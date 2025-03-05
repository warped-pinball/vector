// ------ DATA RETRIEVAL MODULE ------
const dataService = {
  async fetchAllScoresData() {
    try {
      const response = await fetch("/api/scores_page_data");
      if (!response.ok)
        throw new Error("Network error: " + response.statusText);
      const data = await response.json();

      // Store individual sections in localStorage
      localStorage.setItem("/api/leaders", JSON.stringify(data.leaders));
      localStorage.setItem("/api/tournament", JSON.stringify(data.tournament));

      return data;
    } catch (error) {
      console.error("Error fetching scores page data:", error);
      return { leaders: [], tournament: [], claimable: [] };
    }
  },

  async fetchLeaderboardData() {
    const data = await this.fetchAllScoresData();
    return data.leaders;
  },

  async fetchTournamentData() {
    const data = await this.fetchAllScoresData();
    return data.tournament;
  },

  async fetchPersonalData(playerId) {
    if (!playerId || playerId === "null") return [];

    try {
      const response = await fetch("/api/player/scores", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: playerId }),
      });
      if (!response.ok)
        throw new Error("Network error: " + response.statusText);
      const data = await response.json();
      localStorage.setItem(
        `/api/player/scores?id=${playerId}`,
        JSON.stringify(data),
      );
      return data;
    } catch (error) {
      console.error("Error fetching personal scores:", error);
      return [];
    }
  },

  async fetchPlayersData() {
    try {
      const response = await fetch("/api/players");
      if (!response.ok)
        throw new Error("Network error: " + response.statusText);
      return await response.json();
    } catch (error) {
      console.error("Error fetching players:", error);
      return {};
    }
  },

  async fetchClaimableScores() {
    const data = await this.fetchAllScoresData();
    return data.claimable;
  },

  async claimScore(score, initials, playerIndex) {
    try {
      const response = await fetch("/api/scores/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          score: score,
          initials: initials,
          player_index: playerIndex,
        }),
      });
      return response.status === 200;
    } catch (error) {
      console.error("Error claiming score:", error);
      return false;
    }
  },
};

// ------ RENDERING MODULE ------
// [renderer module remains unchanged]

// ------ SCHEDULING MODULE ------
const scheduler = {
  currentRefreshIntervalId: null,

  async refreshAllBoardData() {
    const data = await dataService.fetchAllScoresData();
    renderer.renderLeaderboard(data.leaders);
    renderer.renderTournament(data.tournament);
    renderer.renderClaimableScores(data.claimable);
  },

  async refreshPersonalBoard() {
    const playerId = window.getDropDownValue("playerDropdown");
    const data = await dataService.fetchPersonalData(playerId);
    renderer.renderPersonalScores(data);
  },

  async loadPlayersData() {
    const data = await dataService.fetchPlayersData();
    renderer.renderPlayerDropdown(data);
  },

  startAutoRefresh() {
    this.stopAutoRefresh();
    this.currentRefreshIntervalId = setInterval(() => {
      if (document.getElementById("leaderboardArticles")) {
        this.refreshAllBoardData();
      } else {
        this.stopAutoRefresh();
      }
    }, 10000); // Refresh every 10 seconds
  },

  stopAutoRefresh() {
    if (this.currentRefreshIntervalId) {
      clearInterval(this.currentRefreshIntervalId);
      this.currentRefreshIntervalId = null;
    }
  },

  showTab(tabId) {
    renderer.updateActiveTab(tabId);

    // Personal board requires specific refresh logic
    if (tabId === "personal-board") {
      this.refreshPersonalBoard();
    }
  },

  initialize() {
    // Poll for required elements before starting
    const checkElements = () => {
      if (
        document.getElementById("leaderboardArticles") &&
        document.getElementById("score-board-nav")
      ) {
        // Initial data load
        this.refreshAllBoardData();
        this.loadPlayersData();

        // Start auto-refresh for all data
        this.startAutoRefresh();
      } else {
        setTimeout(checkElements, 100);
      }
    };

    checkElements();
  },
};

// Expose required functions to window
window.showTab = (tabId) => scheduler.showTab(tabId);
window.cleanupRefreshes = () => scheduler.stopAutoRefresh();

// Initialize the application
scheduler.initialize();
