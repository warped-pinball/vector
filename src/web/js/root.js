async function updateTabContent() {
  // Extract the fragment ID from the hash (e.g., '#tab1' -> 'tab1')
  const hash = window.location.hash || "#scores";
  const tabId = hash.replace("#", "");

  // Update the page title based on the tab
  set_tab_title(tabId);

  // Hide all tab content sections first
  set_tab_content(tabId);
}

async function set_tab_title(tabId) {
  const tabTitles = {
    scores: "Scores",
    players: "List",
    about: "About",
    admin: "Admin",
  };
  document.title = tabTitles[tabId] || "Warped Pinball";
}

async function set_tab_content(tabId) {
  // Hide all tab content sections
  document.querySelectorAll(".tab-content").forEach((div) => {
    div.style.display = "none";
  });

  // Show the selected tab content
  const activeTab = document.getElementById(tabId + "_html");
  if (activeTab) {
    activeTab.style.display = "block";
  }
}

// Listen for hash changes (including browser back/forward buttons)
window.addEventListener("hashchange", updateTabContent);

// Load the default (or current) tab only after essential resources are loaded
updateTabContent();

content_mapping = [
  ["/svg/logo.svg.gz", "logo_svg"],
  ["/css/scores.css.gz", "css_files"],
  ["/html/scores.html.gz", "scores_html"],
  ["/js/scores.js.gz", "js_files"],
  ["/html/players.html.gz", "players_html"],
  ["/html/about.html.gz", "about_html"],
  ["/html/admin.html.gz", "admin_html"],
];

// Load the content of the tabs
for (let [url, element_id] of content_mapping) {
  window.loadGzFileIntoElement(url, element_id);
}
