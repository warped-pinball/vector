/**
 * Loads the content for a given tab (e.g., 'tab1') by fetching the compressed HTML file.
 */
async function loadTabContent(tabId) {
  const element_id = "content-" + tabId;

  const url = `./html/${tabId}.html.gz`;
  console.log("Loading tab content: " + url, element_id);
  await loadGzFileIntoElement(url, element_id);
}

/**
 * Determines which tab is currently active based on the hash,
 * then loads and displays the appropriate content.
 * Also updates the page <title>.
 */
async function updateTabContent() {
  // Extract the fragment ID from the hash (e.g., '#tab1' -> 'tab1')
  const hash = window.location.hash || "#scores";
  const tabId = hash.replace("#", "");

  // (Optional) A lookup for our custom tab titles
  const tabTitles = {
    scores: "Scores",
    players: "List",
    about: "About",
    admin: "Admin",
  };

  // Set the document title based on the tab
  // fallback to a default if the tab isn't recognized
  document.title = tabTitles[tabId] || "Warped Pinball";

  // Hide all tab content sections first
  document.querySelectorAll(".tab-content").forEach((div) => {
    div.style.display = "none";
  });

  // Ensure the tab content is loaded, then display it
  await loadTabContent(tabId);
  const activeTab = document.getElementById("content-" + tabId);
  if (activeTab) {
    activeTab.style.display = "block";
  }
}

// Listen for hash changes (including browser back/forward buttons)
window.addEventListener("hashchange", updateTabContent);

// load globally required elements
window.loadGzFileIntoElement = loadGzFileIntoElement;

// Load the default (or current) tab only after essential resources are loaded
updateTabContent();
console.log("Root HTML loaded");
