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
const renderer = {
  renderHeaderRow(containerId, columns, colClass) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const headerArticle = document.createElement("article");
    headerArticle.classList.add("header-row", colClass);

    columns.forEach((col) => {
      const cellDiv = document.createElement("div");
      cellDiv.classList.add(col.key);
      cellDiv.innerText = col.header;
      headerArticle.appendChild(cellDiv);
    });

    container.insertBefore(headerArticle, container.firstChild);
  },

  renderDataRow(item, columns, colClass) {
    const articleRow = document.createElement("article");
    articleRow.classList.add("score-row", colClass);

    columns.forEach((col) => {
      const cellDiv = document.createElement("div");
      cellDiv.classList.add(col.key);

      let value = "";
      if (col.key === "player") {
        const initials = item["initials"] || "";
        const fullName = item["full_name"] || "";
        value = initials;
        if (fullName.trim() !== "") {
          value += ` (${fullName})`;
        }
      } else {
        value = item[col.key] !== undefined ? item[col.key] : "";
      }

      cellDiv.innerText = value;
      cellDiv.setAttribute("title", value);
      articleRow.appendChild(cellDiv);
    });

    return articleRow;
  },

  renderFullArticleList(containerId, data, columns, colClass) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = "";

    this.renderHeaderRow(containerId, columns, colClass);

    data.forEach((item) => {
      const row = this.renderDataRow(item, columns, colClass);
      container.appendChild(row);
    });
  },

  renderLeaderboard(data) {
    const columns = [
      { header: "#", key: "rank" },
      { header: "Score", key: "score" },
      { header: "Player", key: "player" },
      { header: "Ago", key: "ago" },
      { header: "Date", key: "date" },
    ];
    this.renderFullArticleList(
      "leaderboardArticles",
      data,
      columns,
      "five-col",
    );
  },

  renderTournament(data) {
    const columns = [
      { header: "Game", key: "game" },
      { header: "Rank", key: "rank" },
      { header: "Initials", key: "initials" },
      { header: "Score", key: "score" },
    ];
    this.renderFullArticleList(
      "tournamentArticles",
      data,
      columns,
      "four-col-tournament",
    );
  },

  renderPersonalScores(data) {
    const columns = [
      { header: "#", key: "rank" },
      { header: "Score", key: "score" },
      { header: "Ago", key: "ago" },
      { header: "Date", key: "date" },
    ];
    this.renderFullArticleList(
      "personalArticles",
      data,
      columns,
      "four-col-personal",
    );
  },

  async renderPlayerDropdown(playersData) {
    const container = document.getElementById("playerDropdownContainer");
    if (!container) return;

    const dropdownOptions = {};
    Object.entries(playersData).forEach(([id, player]) => {
      let displayName = player.name.trim();
      if (player.initials.trim()) {
        displayName += ` (${player.initials.trim()})`;
      }
      if (displayName) {
        dropdownOptions[id] = displayName;
      }
    });

    const dropDownElement = await window.createDropDownElement(
      "playerDropdown",
      "Select Player",
      dropdownOptions,
      null,
      true,
      (value, text) => {
        console.log(`Player selected => ${value}: ${text}`);
        scheduler.refreshPersonalBoard();
      },
    );

    container.innerHTML = "";
    container.appendChild(dropDownElement);
  },

  renderClaimableScores(data) {
    const claimableScores = document.getElementById("claimable-scores");

    if (data.length === 0) {
      claimableScores.classList.add("hide");
      return;
    }

    claimableScores.innerHTML = "";

    // Add header
    const header = document.createElement("h4");
    header.innerText = "Claimable Scores";
    claimableScores.appendChild(header);

    const playerNumberHeader = document.createElement("article");
    playerNumberHeader.classList.add("game", "claim-header-row");
    playerNumberHeader.innerHTML =
      "<div>Player 1</div><div>Player 2</div><div>Player 3</div><div>Player 4</div>";
    claimableScores.appendChild(playerNumberHeader);

    data.forEach((element) => {
      const game = document.createElement("article");
      game.classList.add("game");

      element.forEach((player) => {
        const playDiv = document.createElement("div");
        playDiv.classList.add("play");

        const initialsDiv = document.createElement("div");
        const scoreDiv = document.createElement("div");
        scoreDiv.innerText = player[1];

        playDiv.appendChild(initialsDiv);
        playDiv.appendChild(scoreDiv);
        game.appendChild(playDiv);

        if (player[0] === "") {
          const claimButton = document.createElement("button");
          claimButton.innerText = "Claim";
          claimButton.classList.add("claim-button");
          claimButton.addEventListener("click", () =>
            this.showClaimModal(player[1], element.indexOf(player)),
          );
          initialsDiv.appendChild(claimButton);
        } else {
          initialsDiv.innerText = player[0];
        }
      });

      claimableScores.appendChild(game);
    });

    claimableScores.classList.remove("hide");
  },

  showClaimModal(score, playerIndex) {
    const modal = document.getElementById("score-claim-modal");

    document.getElementById("score-to-claim").innerText = score;
    document.getElementById("player-number").innerText = playerIndex + 1;

    const submit = document.getElementById("submit-claim-btn");
    const newSubmit = submit.cloneNode(true);
    submit.parentNode.replaceChild(newSubmit, submit);
    newSubmit.id = "submit-claim-btn";

    newSubmit.addEventListener("click", async () => {
      const initials = document.getElementById("initials-input").value;
      const success = await dataService.claimScore(
        score,
        initials,
        playerIndex,
      );

      if (success) {
        scheduler.refreshClaimableScores();
      }
      modal.close();
    });

    modal.showModal();
  },

  updateActiveTab(tabId) {
    // Hide all tab contents
    document.querySelectorAll(".tab-content").forEach((tab) => {
      tab.classList.remove("active");
    });

    // Show selected tab
    const selectedTab = document.getElementById(tabId);
    if (selectedTab) {
      selectedTab.classList.add("active");
    }

    // Update button highlight
    document.querySelectorAll("#score-board-nav button").forEach((button) => {
      button.classList.remove("contrast");
    });

    const activeButton = document.querySelector(
      `button[onclick="window.showTab('${tabId}')"]`,
    );
    if (activeButton) {
      activeButton.classList.add("contrast");
    }
  },
};

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
