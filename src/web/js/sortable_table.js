var tables = document.querySelectorAll('.sortable');

tables.forEach(table => {
    const headers = table.querySelectorAll('th');
    headers.forEach((header, index) => {
        header.addEventListener('click', () => {
            const direction = header.classList.contains('asc') ? 'desc' : 'asc';

            // Clear all chevrons and sort classes from headers
            headers.forEach(th => {
                th.classList.remove('asc', 'desc');
                th.innerHTML = th.innerHTML.replace(/ ▲| ▼/, ''); // Remove any existing chevron
            });

            // Add chevron and sorting class to the clicked header
            header.classList.add(direction);
            header.innerHTML += direction === 'asc' ? ' ▲' : ' ▼';

            sortTable(table, index, direction === 'asc');
        });
    });
});

function sortTable(table, columnIndex, ascending = true) {
    const tbody = table.querySelector('tbody');
    const rows = Array.from(tbody.rows);

    rows.sort((rowA, rowB) => {
        const cellA = rowA.cells[columnIndex].innerText;
        const cellB = rowB.cells[columnIndex].innerText;

        const valueA = isNaN(cellA) ? cellA.toLowerCase() : parseFloat(cellA);
        const valueB = isNaN(cellB) ? cellB.toLowerCase() : parseFloat(cellB);

        if (valueA < valueB) return ascending ? -1 : 1;
        if (valueA > valueB) return ascending ? 1 : -1;
        return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
}
