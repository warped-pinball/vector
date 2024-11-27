// async function fault_check() {
//     const response = await fetch('/install_fault');
//     if (!response.ok) {
//         throw new Error(`HTTP error! Status: ${response.status}`);
//     }
//     const data = await response.text(); // Use .text() to handle plain text responses
//     window.fault_data = data; // Store the raw text data

//     const modal_element = document.getElementById('install_fault_modal'); // Fixed capitalization
//     if (data === "fault") { // Use strict equality check
//         modal_element.classList.add('modal-is-open');
//     } else {
//         console.log("No installation fault:", data);
//     }
// }

// // Wrap in an async function to use await
// (async () => {
//     try {
//         await fault_check();
//     } catch (error) {
//         console.error("Error during fault check:", error);
//     }
// })();