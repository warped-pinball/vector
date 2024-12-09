// 
// Navigation & Resrouce Loading
// 
const pageConfig = {
    'score-boards': {
        title: 'Score Boards',
        resources: [
            { url: '/html/score_boards.html.gz', targetId: 'page_html' },
            { url: '/js/score_boards.js.gz', targetId: 'page_js' },
            { url: '/css/score_boards.css.gz', targetId: 'page_css' },
            { url: '/js/sortable_table.js.gz', targetId: 'extra_js' }
        ]
    },
    'about': {
        title: 'About Warped Pinball',
        resources: [
            { url: '/html/about.html.gz', targetId: 'page_html' },
            { url: '/css/about.css.gz', targetId: 'page_css' }
        ]
    },
    'players': {
        title: 'Players',
        resources: [
            { url: '/html/players.html.gz', targetId: 'page_html' },
            { url: '/js/players.js.gz', targetId: 'page_js' }
        ]
    },
    'admin': {
        title: 'Admin',
        resources: [
            { url: '/html/admin.html.gz', targetId: 'page_html' },
            { url: '/js/admin.js.gz', targetId: 'page_js' },
            { url: '/css/admin.css.gz', targetId: 'page_css' }
        ]
    },
};

let previousResourceIds = [];
let isNavigating = false;
let currentPageKey = null;

async function loadPageResources(pageKey) {
    const config = pageConfig[pageKey];
    if (!config) {
        console.warn(`No config found for page: ${pageKey}`);
        return;
    }
    clearPreviousResources(previousResourceIds);
    const loadPromises = config.resources.map(resource => 
        window.loadResource(resource.url, resource.targetId)
            .then(() => {
                console.log(`Loaded resource: ${resource.url} into ${resource.targetId}`);
                return resource.targetId;
            })
            .catch(error => {
                console.error(`Error loading resource: ${resource.url}`, error);
                throw error;
            })
    );
    try {
        previousResourceIds = await Promise.all(loadPromises);
    } catch (error) {
        console.error('Failed to load all resources:', error);
    }
}

async function handleNavigation(pageKey, replace = false, updateHistory = true) {
    console.log(`handleNavigation called with pageKey: ${pageKey}, replace: ${replace}, updateHistory: ${updateHistory}`);
    if (isNavigating || pageKey === currentPageKey) {
        console.log(`Navigation skipped. isNavigating: ${isNavigating}, currentPageKey: ${currentPageKey}`);
        return;
    }
    isNavigating = true;
    try {
        if (currentPageKey) {
            const cleanupFunction = window[`cleanup_${currentPageKey}`];
            if (typeof cleanupFunction === 'function') {
                console.log(`Cleaning up page: ${currentPageKey}`);
                cleanupFunction();
            }
        }

        const config = pageConfig[pageKey];
        if (!config) {
            console.warn(`No configuration found for page: ${pageKey}`);
            return;
        }

        await set_title(); // Await title setting

        if (updateHistory) {
            const url = `/?page=${pageKey}`;
            if (replace) {
                window.history.replaceState({page: pageKey}, config.title, url);
                console.log(`History replaced with: ${url}`);
            } else {
                window.history.pushState({page: pageKey}, config.title, url);
                console.log(`History pushed with: ${url}`);
            }
        }
        await loadPageResources(pageKey);
        currentPageKey = pageKey;
        console.log(`Navigation to ${pageKey} completed.`);
    } catch (error) {
        console.error(`Error during navigation to ${pageKey}:`, error);
    } finally {
        isNavigating = false;
    }
}

async function set_title() {
    console.log('Setting title...');
    const pageKey = getCurrentPage();
    const config = pageConfig[pageKey];
    if (!config) {
        console.warn(`No config found for page: ${pageKey}`);
        return;
    }
    document.title = config.title;

    try {
        const response = await fetch('/api/game/name');
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const gameName = await response.text();
        const gameNameElem = document.getElementById('game_name');
        if (gameNameElem) {
            gameNameElem.textContent = gameName;
            console.log(`Game name set to: ${gameName}`);
        } else {
            console.warn('Element with ID "game_name" not found.');
        }
        document.title = `${gameName} | ${config.title}`;
    } catch (error) {
        console.error('Failed to load game name:', error);
    }
}

function clearResource(targetId) {
    console.log(`Clearing resource: ${targetId}`);
    const element = document.getElementById(targetId);
    if (!element) {
        console.warn(`Element with ID "${targetId}" not found.`);
        return;
    }
    const placeholder = document.createElement('div');
    placeholder.id = targetId;
    placeholder.style.display = 'none';
    element.replaceWith(placeholder);
    console.log(`Replaced "${targetId}" with a placeholder.`);
}

function clearPreviousResources(resourceIds) {
    resourceIds.forEach(clearResource);
}

function initializeNavigation() {
    const navLinks = [
        { id: 'navigate-score-boards', page: 'score-boards' },
        { id: 'navigate-about', page: 'about' },
        { id: 'navigate-players', page: 'players' },
        { id: 'navigate-admin', page: 'admin' }
    ];
    navLinks.forEach(link => {
        const elem = document.getElementById(link.id);
        if (elem) {
            elem.addEventListener('click', (e) => {
                e.preventDefault();
                console.log(`Navigation link clicked: ${link.page}`);
                handleNavigation(link.page);
            });
            console.log(`Event listener added to: ${link.id}`);
        } else {
            console.warn(`Navigation link element with ID "${link.id}" not found.`);
        }
    });
}

function getCurrentPage() {
    const urlParams = new URLSearchParams(window.location.search);
    const page = urlParams.get('page') || 'score-boards';
    console.log(`Current page determined as: ${page}`);
    return page;
}

function verifyDOMElements(pageKey) {
    const config = pageConfig[pageKey];
    if (!config) {
        console.warn(`No config found for page: ${pageKey}`);
        return false;
    }
    const allExist = config.resources.every(resource => {
        const exists = document.getElementById(resource.targetId) !== null;
        if (!exists) {
            console.warn(`Required element with ID "${resource.targetId}" is missing.`);
        }
        return exists;
    });
    return allExist;
}

async function initializePage() {
    const pageKey = getCurrentPage();
    if (!verifyDOMElements(pageKey)) {
        console.error(`Missing required DOM elements for page: ${pageKey}`);
        return;
    }
    await handleNavigation(pageKey, true, false); // Do not update history on initial load
}

window.onpopstate = async () => {
    console.log('Popstate event triggered.');
    const pageKey = getCurrentPage();
    await handleNavigation(pageKey, false, false);
};

async function init() {
    console.log('Initializing navigation and page...');
    initializeNavigation();
    await initializePage();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
    console.log('Listening for DOMContentLoaded event.');
} else {
    init();
    console.log('Document already loaded. Initializing now.');
}

// Expose functions to window for debugging
window.loadPageResources = loadPageResources;
window.handleNavigation = handleNavigation;
window.set_title = set_title;
window.clearResource = clearResource;
window.clearPreviousResources = clearPreviousResources;
window.initializeNavigation = initializeNavigation;
window.initializePage = initializePage;
window.init = init;
window.toggleTheme = toggleTheme;


// 
// Index.html required js
// 

function setFaviconFromSVGElement(elementId) {
    console.log(`Setting favicon from SVG element: ${elementId}`);
    const svgElement = document.getElementById(elementId);
    if (!svgElement) {
        console.error(`Element with ID "${elementId}" not found.`);
        return;
    }

    const svgString = new XMLSerializer().serializeToString(svgElement);
    const canvas = document.createElement('canvas');
    canvas.width = 32;
    canvas.height = 32;
    const ctx = canvas.getContext('2d');

    const svgBlob = new Blob([svgString], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();

    img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);

        const pngDataURL = canvas.toDataURL('image/png');
        let favicon = document.querySelector("link[rel='icon']") || document.createElement('link');
        favicon.rel = 'icon';
        favicon.href = pngDataURL;
        document.head.appendChild(favicon);
        console.log('Favicon set successfully.');
    };

    img.onerror = (error) => {
        console.error('Failed to load SVG for favicon:', error);
    };

    img.src = url;
}

setTimeout(() => {
    try {
        setFaviconFromSVGElement('logo');
    } catch (error) {
        console.error('Error setting favicon:', error);
    }
}, 1000);

function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    const button = document.querySelector('button[onclick="window.toggleTheme()"]');
    button.textContent = newTheme === 'dark' ? '🌙' : '☀️';
}





// 
// Authentication and Routing
// 

async function authenticateAndFetch(password, url, data = null) {
    // Get challenge
    const challengeResponse = await fetch("/api/auth/challenge");
    if (!challengeResponse.ok) {
        throw new Error("Failed to get challenge.");
    }
    const challengeData = await challengeResponse.json();
    const challenge = challengeData.challenge;
  
    const urlObj = new URL(url, window.location.origin);
    const path = urlObj.pathname;
    const queryString = urlObj.search;
    const requestBodyString = data ? JSON.stringify(data) : "";
    
    // Message must match the server construction
    const message = challenge + path + queryString + requestBodyString;
  
    // Compute HMAC using js-sha256
    const hmacHex = sha256.hmac(password, message);  
  
    const headers = {
      "X-Auth-HMAC": hmacHex,
      "Content-Type": "application/json"
    };
  
    const method = data ? "POST" : "GET";
  
    const response = await fetch(url, {
      method: method,
      headers: headers,
      body: requestBodyString || undefined
    });
  
    return response;
}

window.authenticateAndFetch = authenticateAndFetch;

// 
// Page Element js utilities
// 

// Add a dropdown option dynamically
async function addDropDownOption(dropDownElement, value, text) {
    const ulElement = dropDownElement.querySelector('ul');
    const listItem = document.createElement('li');
    const anchorElement = document.createElement('a');

    anchorElement.innerText = text;
    anchorElement.dataset.value = value;
    anchorElement.href = "#";

    // Add click event to select this option
    anchorElement.addEventListener('click', (event) => {
        event.preventDefault(); // Prevent default navigation
        setDropDownValue(dropDownElement, value, text);
    });

    listItem.appendChild(anchorElement);
    ulElement.appendChild(listItem);
}

// Get the currently selected dropdown value
function getDropDownValue(dropDownElement) {
    return dropDownElement.dataset.selectedValue || null;
}

// Set the dropdown value when an option is clicked
function setDropDownValue(dropDownElement, value, text) {
    const summaryElement = dropDownElement.querySelector('summary');
    summaryElement.innerText = text;
    dropDownElement.dataset.selectedValue = value; // Store the value
    dropDownElement.removeAttribute("open"); // Close the dropdown
}

// Create a dropdown element from a key-value mapping
async function createDropDownElement(id, summaryText, options, defaultValue = null) {
    const dropDownElement = document.createElement('details');
    dropDownElement.id = id;
    dropDownElement.className = "dropdown";
    dropDownElement.dataset.selectedValue = ""; // Initialize no selection

    const summaryElement = document.createElement('summary');
    summaryElement.innerText = summaryText;

    const ulElement = document.createElement('ul');

    // Add options to the dropdown
    for (const [value, text] of Object.entries(options)) {
        await addDropDownOption(dropDownElement, value, text);
        // Pre-select the default value if it matches
        if (defaultValue === value) {
            setDropDownValue(dropDownElement, value, text);
        }
    }

    dropDownElement.appendChild(summaryElement);
    dropDownElement.appendChild(ulElement);

    return dropDownElement; // Return the dropdown element for placement
}

window.addDropDownOption = addDropDownOption;
window.getDropDownValue = getDropDownValue;
window.setDropDownValue = setDropDownValue;
window.createDropDownElement = createDropDownElement;
