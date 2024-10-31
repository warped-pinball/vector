const pageConfig = {
    'leader-board': {
        title: 'Leader Board',
        resources: [
            { url: '/html/leader_board.html.gz', targetId: 'page_html' },
            { url: '/js/leader_board.js.gz', targetId: 'page_js' },
            { url: '/js/sortable_table.js.gz', targetId: 'extra_js' },
            { url: '/css/leader_board.css.gz', targetId: 'page_css' }
        ]
    },
    'about': {
        title: 'About Warped Pinball',
        resources: [
            { url: '/html/about.html.gz', targetId: 'page_html' },
            { url: '/css/about.css.gz', targetId: 'page_css' }
        ]
    }
};

let previousResourceIds = [];
let isNavigating = false;
let currentPageKey = null;

async function loadPageResources(pageKey) {
    const config = pageConfig[pageKey];
    if (!config) return;
    clearPreviousResources(previousResourceIds);
    const newResourceIds = [];
    for (const resource of config.resources) {
        await window.loadResource(resource.url, resource.targetId);
        newResourceIds.push(resource.targetId);
    }
    previousResourceIds = newResourceIds;
}

async function handleNavigation(pageKey, replace = false, updateHistory = true) {
    if (isNavigating || pageKey === currentPageKey) return;
    isNavigating = true;
    try {
        if (currentPageKey) {
            const cleanupFunction = window[`cleanup_${currentPageKey}`];
            if (typeof cleanupFunction === 'function') {
                cleanupFunction();
            }
        }

        const config = pageConfig[pageKey];
        if (!config) return;
        
        set_title();

        if (updateHistory) {
            const url = `/?page=${pageKey}`;
            if (replace) {
                window.history.replaceState({}, config.title, url);
            } else {
                window.history.pushState({}, config.title, url);
            }
        }
        await loadPageResources(pageKey);
        currentPageKey = pageKey;
    } finally {
        isNavigating = false;
    }
}

async function set_title() {
    const pageKey = getCurrentPage();
    const config = pageConfig[pageKey];
    document.title = config.title;
    document.getElementById('page_title').innerText = config.title;
    fetch('/GameName')
        .then(response => response.json())
        .then(data => {
            const gameName = data.gamename; 
            document.getElementById('game_name').textContent = gameName;
            document.title = gameName + ' - ' + config.title;
        })
        .catch(error => {
            console.error('Failed to load game name:', error)
        });
}

function clearResource(targetId) {
    const element = document.getElementById(targetId);
    if (!element) return;
    const placeholder = document.createElement('div');
    placeholder.id = targetId;
    placeholder.style.display = 'none';
    element.replaceWith(placeholder);
}

function clearPreviousResources(resourceIds) {
    resourceIds.forEach(clearResource);
}

function initializeNavigation() {
    const navLinks = [
        { id: 'navigate-leader-board', page: 'leader-board' },
        { id: 'navigate-about', page: 'about' }
    ];
    navLinks.forEach(link => {
        const elem = document.getElementById(link.id);
        if (elem) {
            elem.addEventListener('click', (e) => {
                e.preventDefault();
                handleNavigation(link.page);
            });
        }
    });
}

function getCurrentPage() {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('page') || 'leader-board';
}

async function initializePage() {
    const pageKey = getCurrentPage();
    await handleNavigation(pageKey, true, true);
}

window.onpopstate = async () => {
    const pageKey = getCurrentPage();
    await handleNavigation(pageKey, false, false);
};

async function init() {
    initializeNavigation();
    await initializePage();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

function setFaviconFromSVGElement(elementId) {
    // Find the SVG element by ID
    const svgElement = document.getElementById(elementId);
    if (!svgElement) {
        console.error(`Element with ID "${elementId}" not found.`);
        return;
    }

    // Serialize the SVG element to a string
    const svgString = new XMLSerializer().serializeToString(svgElement);

    // Create a canvas to draw the SVG onto
    const canvas = document.createElement('canvas');
    canvas.width = 32; // Set desired favicon size (e.g., 32x32)
    canvas.height = 32;
    const ctx = canvas.getContext('2d');

    // Convert SVG string to a data URL and load it into an image
    const svgBlob = new Blob([svgString], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(svgBlob);
    const img = new Image();

    img.onload = () => {
        // Draw the SVG image onto the canvas
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url); // Release the blob URL

        // Convert the canvas to a PNG data URL
        const pngDataURL = canvas.toDataURL('image/png');

        // Update or create the favicon link element
        let favicon = document.querySelector("link[rel='icon']") || document.createElement('link');
        favicon.rel = 'icon';
        favicon.href = pngDataURL;
        document.head.appendChild(favicon);
    };

    img.src = url; // Start loading the SVG image
}

// Usage
setFaviconFromSVGElement('logo');


// Expose functions to window for debugging
window.loadPageResources = loadPageResources;
window.handleNavigation = handleNavigation;
window.set_title = set_title;
window.clearResource = clearResource;
window.clearPreviousResources = clearPreviousResources;
window.initializeNavigation = initializeNavigation;
window.initializePage = initializePage;
window.init = init;
window.setFaviconFromSVGElement = setFaviconFromSVGElement;

