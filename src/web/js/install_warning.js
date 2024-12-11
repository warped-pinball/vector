async function fault_check() {
    const response = await fetch('/api/fault');
    if (response.status !== 200) { // Use strict equality check
        alert('Something has gone wrong while checking for installation issues. Refresh the page and if the issue persists please contact inventingfun@gmail.com');
    }
    const data = await response.json(); // list of faults as ["fault1", "fault2", ...]

    const modal_element = document.getElementById('install_warning_modal'); 
    if (data.length > 0) {
        const fault_list = document.getElementById('fault_list');
        fault_list.innerHTML = ''; // Clear any existing faults

        // Create a list item for each fault and append it to the fault_list
        data.forEach(fault => {
            const fault_item = document.createElement('div');
            fault_item.textContent = fault;
            fault_list.appendChild(fault_item);
        });

        modal_element.setAttribute('open', ''); // Add the "open" attribute to the dialog
        console.log("Installation fault detected");
    } else {
        console.log("No installation fault:", data);
    }
}

fault_check();
