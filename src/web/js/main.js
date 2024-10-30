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

    async function navigateToPage(pageKey) {
        console.log('Navigating to page:', pageKey);
        const config = pageConfig[pageKey];
        if (!config) {
            console.error('Invalid page key:', pageKey);
            return;
        }
        const { title, resources } = config;
        document.title = title;
        window.history.pushState({}, title, `/?page=${pageKey}`);
        clearPreviousResources(previousResourceIds);
        const newResourceIds = [];

        for (const resource of resources) {
            await window.loadResource(resource.url, resource.targetId);
            newResourceIds.push(resource.targetId);
        }

        previousResourceIds = newResourceIds;
    }
    // make navigateToPage available to the window object
    window.navigateToPage = navigateToPage;

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
                    navigateToPage(link.page);
                });
            }
        });
    }

    async function initializePage() {
        const urlParams = new URLSearchParams(window.location.search);
        const pageKey = urlParams.get('page') || 'leader_board';
        await navigateToPage(pageKey);
    }

    window.onpopstate = async () => {
        const urlParams = new URLSearchParams(window.location.search);
        const pageKey = urlParams.get('page') || 'leader_board';
        await navigateToPage(pageKey);
    };

    document.addEventListener('DOMContentLoaded', () => {
        initializeNavigation();
        initializePage();
    });
})();
