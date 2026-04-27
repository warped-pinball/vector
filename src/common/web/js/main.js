//
// DOM Helpers
//
function waitForElementById(id, timeout = 2000) {
  return new Promise((resolve, reject) => {
    const existing = document.getElementById(id);
    if (existing) {
      resolve(existing);
      return;
    }
    const observer = new MutationObserver(() => {
      const el = document.getElementById(id);
      if (el) {
        clearTimeout(timer);
        observer.disconnect();
        resolve(el);
      }
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
    });
    const timer = setTimeout(() => {
      observer.disconnect();
      reject(
        new Error(`Element with id "${id}" not found within ${timeout}ms`),
      );
    }, timeout);
  });
}

window.waitForElementById = waitForElementById;

//
// Page Element JS utilities
//

// Create a dropdown option dynamically
async function createDropDownOption(value, text, callback = null) {
  const listItem = document.createElement("li");
  const anchorElement = document.createElement("a");

  anchorElement.innerText = text;
  anchorElement.dataset.value = value;
  anchorElement.href = "#";

  anchorElement.addEventListener("click", (event) => {
    event.preventDefault();
    const dropDownElement = anchorElement.closest("details");
    setDropDownValue(dropDownElement, value, text);
    if (typeof callback === "function") {
      callback(value, text);
    }
  });

  listItem.appendChild(anchorElement);
  return listItem;
}

// Get the currently selected dropdown value
function getDropDownValue(dropDownElementID) {
  return document.getElementById(dropDownElementID).dataset.selectedValue;
}

// Set the dropdown value when an option is clicked
function setDropDownValue(dropDownElement, value, text, validate = true) {
  if (typeof dropDownElement === "string") {
    dropDownElement = document.getElementById(dropDownElement);
  }

  if (validate) {
    const optionElements = dropDownElement.querySelectorAll("a");
    let found = false;
    for (const optionElement of optionElements) {
      if (optionElement.dataset.value === value) {
        found = true;
        break;
      }
    }
    if (!found) {
      console.error(`Value ${value} not found in dropdown options.`);
      return;
    }
  }

  const summaryElement = dropDownElement.querySelector("summary");
  summaryElement.innerText = text;
  dropDownElement.dataset.selectedValue = value;
  dropDownElement.removeAttribute("open");
}

// Create a dropdown element from a key-value mapping
async function createDropDownElement(
  id,
  summaryText,
  options,
  defaultValue = null,
  sortOptions = false,
  optionsCallback = null,
) {
  const dropDownElement = document.createElement("details");
  dropDownElement.id = id;
  dropDownElement.className = "dropdown";
  dropDownElement.dataset.selectedValue = "";

  const summaryElement = document.createElement("summary");
  summaryElement.innerText = summaryText;

  const ulElement = document.createElement("ul");

  let entries = Array.isArray(options)
    ? options.map((val) => [val, val])
    : Object.entries(options);

  if (sortOptions) {
    entries = entries.sort((a, b) => String(a[1]).localeCompare(String(b[1])));
  }

  for (const [value, text] of entries) {
    const listItem = await createDropDownOption(value, text, optionsCallback);
    ulElement.appendChild(listItem);
    if (defaultValue === value) {
      setDropDownValue(dropDownElement, value, text);
    }
  }

  dropDownElement.appendChild(summaryElement);
  dropDownElement.appendChild(ulElement);

  return dropDownElement;
}

window.getDropDownValue = getDropDownValue;
window.setDropDownValue = setDropDownValue;
window.createDropDownElement = createDropDownElement;

//
// Authentication
//
async function showPasswordPrompt() {
  return new Promise((resolve) => {
    const dialog = document.getElementById("password_modal");
    const passwordInput = document.getElementById("admin_password_input");
    const saveButton = document.getElementById("password_save_button");
    const cancelButton = document.getElementById("password_cancel_button");

    passwordInput.value = "";

    function onSave() {
      const password = passwordInput.value.trim();

      if (document.getElementById("stay_logged_in").checked) {
        localStorage.setItem("password", password);
        const logoutButton = document.getElementById("logout-button");
        if (logoutButton) {
          logoutButton.classList.remove("hide");
        }
      } else {
        localStorage.removeItem("password");
        const logoutButton = document.getElementById("logout-button");
        if (logoutButton) {
          logoutButton.classList.add("hide");
        }
      }

      cleanup();
      resolve(password);
    }

    function onCancel() {
      cleanup();
      resolve(null);
    }

    function cleanup() {
      saveButton.removeEventListener("click", onSave);
      cancelButton.removeEventListener("click", onCancel);
      dialog.close();
    }

    saveButton.addEventListener("click", onSave);
    cancelButton.addEventListener("click", onCancel);

    dialog.showModal();
  });
}

async function get_password() {
  let password = localStorage.getItem("password");

  if (password === null) {
    password = await showPasswordPrompt();
  } else {
    const logoutButton = document.getElementById("logout-button");
    if (logoutButton) {
      logoutButton.classList.remove("hide");
    }
  }

  return password;
}

async function logout() {
  localStorage.removeItem("password");
  const logoutButton = document.getElementById("logout-button");
  if (logoutButton) {
    logoutButton.classList.add("hide");
  }
}

// Show logout button if password is already stored
if (localStorage.getItem("password")) {
  const logoutButton = document.getElementById("logout-button");
  if (logoutButton) {
    logoutButton.classList.remove("hide");
  }
}

window.get_password = get_password;
window.logout = logout;

//
// Theme
//
function toggleTheme() {
  const html = document.documentElement;
  const currentTheme = html.getAttribute("data-theme");
  const newTheme = currentTheme === "dark" ? "light" : "dark";
  html.setAttribute("data-theme", newTheme);
}

window.toggleTheme = toggleTheme;

//
// Logo & Favicon
//
async function setFaviconFromSVGString(svgString) {
  const canvas = document.createElement("canvas");
  canvas.width = 32;
  canvas.height = 32;
  const ctx = canvas.getContext("2d");

  const svgBlob = new Blob([svgString], { type: "image/svg+xml" });
  const url = URL.createObjectURL(svgBlob);
  const img = new Image();

  img.onload = () => {
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);

    const pngDataURL = canvas.toDataURL("image/png");
    const favicon =
      document.querySelector("link[rel='icon']") ||
      document.createElement("link");
    favicon.rel = "icon";
    favicon.href = pngDataURL;
    document.head.appendChild(favicon);
  };

  img.onerror = (error) => {
    URL.revokeObjectURL(url);
    console.error("Failed to load SVG for favicon:", error);
  };

  img.src = url;
}

async function loadLogo() {
  try {
    const svgText = await fetchGzip("/svg/logo.svg");
    const blob = new Blob([svgText], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const logo = document.getElementById("logo");
    if (logo) {
      logo.src = url;
    }
    await setFaviconFromSVGString(svgText);
  } catch (error) {
    console.error("Failed to load logo:", error);
  }
}

//
// Version display
//
async function set_version() {
  const response = await window.smartFetch(
    "/api/version",
    (data = null),
    (auth = false),
  );
  const version = await response.json();
  document.getElementById("version").innerText = "Vector " + version["version"];
}

//
// Peer discovery & game-name header
//
async function get_peers() {
  const response = await window.smartFetch(
    "/api/network/peers",
    (data = null),
    (auth = false),
  );
  const peers = await response.json();
  return peers;
}

window.get_peers = get_peers;

async function set_game_name() {
  const raw_peers = await get_peers();

  const peers = {};
  let own_name = null;
  for (const [ip, peer] of Object.entries(raw_peers)) {
    if (!peer.self) {
      peers[ip] = peer.name;
    } else {
      own_name = peer.name;
    }
  }

  // Set page title
  if (own_name) {
    document.title = `${own_name} | ${document.title}`;
  }

  if (Object.keys(raw_peers).length <= 1) {
    if (Object.keys(raw_peers).length === 1) {
      const game_name = document.createElement("strong");
      game_name.innerText = Object.values(raw_peers)[0].name;
      const game_name_element = document.getElementById("game_name");
      game_name_element.replaceWith(game_name);
      game_name.id = "game_name";
    }
    return;
  }

  const navigateToPeer = async (ip) => {
    const url = "http://" + ip + window.location.pathname;
    window.location.href = url;
  };

  const dropDownElement = await createDropDownElement(
    "game_name",
    "Select Peer",
    peers,
    null,
    true,
    navigateToPeer,
  );
  dropDownElement.style.margin = 0;
  const gameNameElement = document.getElementById("game_name");
  gameNameElement.replaceWith(dropDownElement);

  if (own_name) {
    setDropDownValue(dropDownElement, own_name, own_name, false);
  }
}

window.set_game_name = set_game_name;

//
// Initialise shared layout
//
async function initSharedLayout() {
  set_version();
  await set_game_name();
  await loadLogo();
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initSharedLayout);
} else {
  initSharedLayout();
}

// Refresh peer dropdown every minute
setInterval(set_game_name, 60000);
