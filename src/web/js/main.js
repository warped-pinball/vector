const pageConfig = {
    'score-boards': {
        title: 'Score Boards',
        resources: [
            { url: '/html/score_boards.html.gz', targetId: 'page_html' },
            { url: '/js/score_boards.js.gz', targetId: 'page_js' },
            { url: '/js/sortable_table.js.gz', targetId: 'extra_js' },
            { url: '/css/score_boards.css.gz', targetId: 'page_css' }
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
    'settings': {
        title: 'Settings',
        resources: [
            { url: '/html/settings.html.gz', targetId: 'page_html' },
            { url: '/js/settings.js.gz', targetId: 'page_js' },
            // { url: '/css/settings.css.gz', targetId: 'page_css' }
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
    const pageTitleElem = document.getElementById('page_title');
    if (pageTitleElem) {
        pageTitleElem.innerText = config.title;
        console.log(`Page title set to: ${config.title}`);
    } else {
        console.warn('Element with ID "page_title" not found.');
    }

    try {
        const response = await fetch('/GameName');
        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }
        const data = await response.json();
        const gameName = data.gamename;
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
        { id: 'navigate-settings', page: 'settings' }
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
