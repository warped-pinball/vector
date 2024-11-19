const response = await fetch('/install_fault');
if (!response.ok) {
    throw new Error(`HTTP error! Status: ${response.status}`);
}
const data = await response.json();

if (data){
    const modal = Document.getElementById('install_fault_modal')
    modal.classList.add('modal-is-open')
}
