async function configure_check() {
    const response = await fetch('/api/in_ap_mode');
    // if we get a 404, we are not in AP mode
    if (response.status === 404) {
        return;
    }

    if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
    }

    const modal_element = document.getElementById('configure_modal'); // Fixed capitalization
    modal_element.setAttribute('open', ''); // Add the "open" attribute to the dialog
}

configure_check();
