async function fault_check() {
    const response = await fetch('/api/fault');
    if (!response.ok) {
        throw new Error(`HTTP error! Status: ${response.status}`);
    }
    const data = await response.text(); // Use .text() to handle plain text responses
    window.fault_data = data; // Store the raw text data

    const modal_element = document.getElementById('install_warning_modal'); // Fixed capitalization
    if (data === "fault") { // Use strict equality check
        modal_element.setAttribute('open', ''); // Add the "open" attribute to the dialog
        console.log("Installation fault detected");
    } else {
        console.log("No installation fault:", data);
    }
}

fault_check();
