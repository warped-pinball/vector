// Navigation management function to switch pages
const pageConfig = {
    'leader_board': {
        title: 'Leader Board',
        url: '/leaderboard',
        resources: [
            { url: '/html/leader_board.html.gz', type: 'html', targetId: 'content' },
            { url: '/js/leader_board.js.gz', type: 'js', targetId: 'custom_script' },
            { url: '/css/score_board.css.gz', type: 'css', targetId: 'custom_styles' }
        ]
    },
    'about': {
        title: 'About Us',
        url: '/about',
        resources: [
            { url: '/zip/about_content.html.gz', type: 'html', targetId: 'content' },
            { url: '/zip/about_styles.css.gz', type: 'css', targetId: 'custom_styles' }
        ]
    }
};

// Stores the IDs of elements created during the page load to clean up before switching pages
let previousResources = [];

window.navigateToPage = async function(pageKey) {
    const { title, resources } = pageConfig[pageKey];

    // Update title and browser history with the query parameter
    document.title = title;
    window.history.pushState({}, title, `/?page=${pageKey}`);

    // Clear previously loaded resources
    clearPreviousResources();

    // Replace page content as per resources defined
    for (const resource of resources) {
        await loadResource(resource.url, resource.type, resource.targetId);
        previousResources.push(resource.targetId); // Track the ID for cleanup
    }
};

// Function to clear previously loaded resources
function clearPreviousResources() {
    previousResources.forEach(targetId => {
        const element = document.getElementById(targetId);
        if (element) {
            element.innerHTML = ''; // Clear content of the element
            if (element.tagName !== 'STYLE') {
                element.remove(); // Remove element if not a <style> tag
            }
        }
    });
    previousResources = []; // Reset the previousResources array
}

// Helper function to load a resource into the DOM
async function loadResource(url, type, targetId) {
    const response = await fetch(url);
    const data = await response.text();

    let newElement;
    switch (type) {
        case "css":
            newElement = document.createElement("style");
            newElement.textContent = data;
            newElement.id = targetId;
            break;
        case "script":
            newElement = document.createElement("script");
            newElement.textContent = data;
            newElement.id = targetId;
            break;
        case "html":
            newElement = document.createElement("div");
            newElement.innerHTML = data;
            newElement.id = targetId;
            break;
        default:
            console.error(`Unsupported resource type: ${type}`);
            return;
    }

    const targetElement = document.getElementById(targetId);
    if (targetElement) {
        targetElement.replaceWith(newElement);
    } else {
        document.body.appendChild(newElement); // Append if target element not found
    }
}

// Load page on initial load based on URL parameter
document.addEventListener('DOMContentLoaded', async () => {
    const urlParams = new URLSearchParams(window.location.search);
    const pageKey = urlParams.get('page') || 'leader_board';
    await navigateToPage(pageKey);
});

// Utility to set up navigation links
function link_nav(id, page) {
    document.getElementById(id).addEventListener('click', (event) => {
        event.preventDefault(); // Prevent default anchor behavior
        navigateToPage(page);
    });
}

// Setup navigation links
link_nav('navigate-leader-board', 'leader_board');
link_nav('navigate-about', 'about');
