// 
// Navigation & Resrouce Loading
// 
const pageConfig = {
    'scores': {
        title: 'Scores',
        resources: [
            { url: '/html/scores.html.gz', targetId: 'page_html' },
            { url: '/js/scores.js.gz', targetId: 'page_js' },
            { url: '/js/sortable_table.js.gz', targetId: 'extra_js' }
        ]
    },
    'about': {
        title: 'About Warped Pinball',
        resources: [
            { url: '/html/about.html.gz', targetId: 'page_html' }
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
        fetchDecompressAndApply(resource.url, resource.targetId)
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
        { id: 'navigate-scores', page: 'scores' },
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
    const page = urlParams.get('page') || 'scores';
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
// Authentication
// 
async function showPasswordPrompt() {
    return new Promise((resolve) => {
        const dialog = document.getElementById("password_modal");
        const passwordInput = document.getElementById("admin_password_input");
        const saveButton = document.getElementById("password_save_button");
        const cancelButton = document.getElementById("password_cancel_button");

        // Clear previous value from input just in case
        passwordInput.value = "";

        // Function to handle saving password
        function onSave() {
            const password = passwordInput.value.trim();
            
            // if stay logged in is checked, store password in local storage
            if (document.getElementById("stay_logged_in").checked) {
                // store password in local storage
                localStorage.setItem("password", password);
        
                // un-hide the logout button since we now have a stored password
                const logoutButton = document.getElementById("logout-button");
                if (logoutButton) {
                    logoutButton.classList.remove("hide");
                }
            } else {
                // remove password from local storage
                localStorage.removeItem("password");
        
                // Hide the logout button
                const logoutButton = document.getElementById("logout-button");
                if (logoutButton) {
                    logoutButton.classList.add("hide");
                }
            }

            cleanup();
            resolve(password);
        }

        // Function to handle cancel
        function onCancel() {
            cleanup();
            resolve(null);
        }

        // Cleanup event listeners and close dialog
        function cleanup() {
            saveButton.removeEventListener("click", onSave);
            cancelButton.removeEventListener("click", onCancel);
            dialog.close();
        }

        // Add event listeners
        saveButton.addEventListener("click", onSave);
        cancelButton.addEventListener("click", onCancel);

        // Show the modal
        dialog.showModal();
    });
}

async function get_password() {
    // check if password is already in localStorage
    let password = localStorage.getItem("password");

    if (!password) {
        password = await showPasswordPrompt();

        // If user canceled, password is null, so handle that if needed
        if (password !== null) {
            // password is now stored in localStorage by showPasswordPrompt
            console.log("Password set:", password);
        } else {
            console.log("User canceled password input.");
        }
    } else {
        // un-hide the logout button if password is already stored
        const logoutButton = document.getElementById("logout-button");
        if (logoutButton) {
            logoutButton.classList.remove("hide");
        }
    }

    console.log("Password: ", password);
    return password;
}

async function logout() {
    // remove password from local storage
    localStorage.removeItem("password");

    // Hide the logout button again if desired
    const logoutButton = document.getElementById("logout-button");
    if (logoutButton) {
        logoutButton.classList.add("hide");
    }
}

// Call get_password on load
if (localStorage.getItem("password")) {
    // un-hide the logout button
    const logoutButton = document.getElementById("logout-button");
    if (logoutButton) {
        logoutButton.classList.remove("hide");
    }
}

// Make functions accessible from window
window.get_password = get_password;
window.logout = logout;


// 
// Page Element js utilities
// 

// Create a dropdown option dynamically
async function createDropDownOption(value, text) {
    const listItem = document.createElement('li');
    const anchorElement = document.createElement('a');

    anchorElement.innerText = text;
    anchorElement.dataset.value = value;
    anchorElement.href = "#";

    // Add click event to select this option
    anchorElement.addEventListener('click', (event) => {
        event.preventDefault(); // Prevent default navigation
        const dropDownElement = anchorElement.closest('details');
        setDropDownValue(dropDownElement, value, text);
    });

    listItem.appendChild(anchorElement);
    return listItem;
}

// Get the currently selected dropdown value
function getDropDownValue(dropDownElementID) {
    // get the attribute data-selected-value
    return document.getElementById(dropDownElementID).dataset.selectedValue;
}

// Set the dropdown value when an option is clicked
function setDropDownValue(dropDownElement, value, text) {    
    // if dropDownElement is a string, get the element
    if (typeof dropDownElement === 'string') {
        dropDownElement = document.getElementById(dropDownElement);
    }    

    // check that value is one of the options
    const optionElements = dropDownElement.querySelectorAll('a');
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

    const summaryElement = dropDownElement.querySelector('summary');
    summaryElement.innerText = text;
    dropDownElement.dataset.selectedValue = value; // Store the value
    dropDownElement.removeAttribute("open"); // Close the dropdown
}

// Create a dropdown element from a key-value mapping
async function createDropDownElement(id, summaryText, options, defaultValue = null, sortOptions = false) {
    const dropDownElement = document.createElement('details');
    dropDownElement.id = id;
    dropDownElement.className = "dropdown";
    dropDownElement.dataset.selectedValue = ""; // Initialize no selection

    const summaryElement = document.createElement('summary');
    summaryElement.innerText = summaryText;

    const ulElement = document.createElement('ul');

    // Convert options to an array of entries
    let entries = Array.isArray(options) ? options.map(val => [val, val]) : Object.entries(options);

    // Sort entries if required
    if (sortOptions) {
        entries = entries.sort((a, b) => a[1].localeCompare(b[1]));
    }

    // Add options to the dropdown
    for (const [value, text] of entries) {
        const listItem = await createDropDownOption(value, text);
        ulElement.appendChild(listItem);
        // Pre-select the default value if it matches
        if (defaultValue === value) {
            setDropDownValue(dropDownElement, value, text);
        }
    }

    dropDownElement.appendChild(summaryElement);
    dropDownElement.appendChild(ulElement);

    return dropDownElement; // Return the dropdown element for placement
}

window.addDropDownOption = createDropDownElement;
window.getDropDownValue = getDropDownValue;
window.setDropDownValue = setDropDownValue;
window.createDropDownElement = createDropDownElement;
