async function configure_check() {
    const response = await fetch('/api/in_ap_mode');
    const data = await response.json();
    if (data.in_ap_mode) {
        const modal_element = document.getElementById('configure_modal'); // Fixed capitalization
        modal_element.setAttribute('open', ''); // Add the "open" attribute to the dialog
    }
}

configure_check();
