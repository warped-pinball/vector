// main.js

(async () => {
    const pageConfig = {
        'leader_board': {
            title: 'Leader Board',
            resources: [
                { url: '/html/leader_board.html.gz', targetId: 'page_html' },
                { url: '/js/leader_board.js.gz', targetId: 'page_js' },
                { url: '/css/score_board.css.gz', targetId: 'page_css' }
            ]
        },
        'about': {
            title: 'About Us',
            resources: [
                { url: '/html/about.html.gz', targetId: 'page_html' },
                // { url: '/css/about.css.gz', targetId: 'page_css' }
            ]
        }
    };

    let previousResourceIds = [];
    let isNavigating = false;

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

    async function handleNavigation(pageKey, replace = false) {
        if (isNavigating) return;
        isNavigating = true;
        try {
            const config = pageConfig[pageKey];
            if (!config) return;
            document.title = config.title;
            const url = `/?page=${pageKey}`;
            if (replace) {
                window.history.replaceState({}, config.title, url);
            } else {
                window.history.pushState({}, config.title, url);
            }
            await loadPageResources(pageKey);
        } finally {
            isNavigating = false;
        }
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
            { id: 'navigate-leader-board', page: 'leader_board' },
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

    async function initializePage() {
        const urlParams = new URLSearchParams(window.location.search);
        const pageKey = urlParams.get('page') || 'leader_board';
        await handleNavigation(pageKey, true);
    }

    window.onpopstate = async () => {
        const urlParams = new URLSearchParams(window.location.search);
        const pageKey = urlParams.get('page') || 'leader_board';
        await handleNavigation(pageKey);
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

    // Expose functions to window for debugging
    window.loadPageResources = loadPageResources;
    window.handleNavigation = handleNavigation;
    window.clearResource = clearResource;
    window.clearPreviousResources = clearPreviousResources;
    window.initializeNavigation = initializeNavigation;
    window.initializePage = initializePage;
    window.init = init;
})();
