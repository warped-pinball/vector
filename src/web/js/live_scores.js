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

  // If score changed, update the CSS variable to animate
  if (newScore !== oldScore) {
    scoreElement.style.setProperty("--num", newScore);

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

  // If game not active, hide status and exit
  if (data.GameActive !== true) {
    gameStatus.classList.add("hide");
    return;
  }

  // Game is active, show the container
  gameStatus.classList.remove("hide");

  // Process player scores
  const players = document.getElementById("live-players");
  for (const tag of players.children) {
    const playerId = tag.id.split("-")[2];
    const scoreElement = document.getElementById(
      `live-player-${playerId}-score`,
    );
    const newScore = data.Scores[playerId - 1];

    // Hide players with no score
    if (newScore === undefined || newScore === 0) {
      tag.classList.add("hide");
      continue;
    }

    // Show player and update score
    tag.classList.remove("hide");
    scoreElement.classList.add("css-score-anim");
    window.processScoreChange(scoreElement, playerId, newScore);
  }

  // Update ball in play display
  window.updateBallInPlay(data);
};

// Initial call
window.getGameStatus();

// Poll for updates
setInterval(window.getGameStatus, 1500);
