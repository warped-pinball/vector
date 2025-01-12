function attachTableSortingAndDownloading() {
    const tables = document.querySelectorAll('.sortable, .downloadable');

    tables.forEach(table => {
        // Prevent re-initialization on the same table
        if (table.dataset.enhanced === 'true') {
            return;
        }
        table.dataset.enhanced = 'true';

        // Attach sorting if .sortable
        if (table.classList.contains('sortable')) {
            const headers = table.querySelectorAll('th');
            headers.forEach((header, index) => {
                header.addEventListener('click', () => {
                    const direction = header.classList.contains('asc') ? 'desc' : 'asc';

                    // Clear all chevrons and sort classes
                    headers.forEach(th => {
                        th.classList.remove('asc', 'desc');
                        th.innerHTML = th.innerHTML.replace(/ ▲| ▼/, '');
                    });

                    // Add chevron and class to the clicked header
                    header.classList.add(direction);
                    header.innerHTML += direction === 'asc' ? ' ▲' : ' ▼';

                    sortTable(table, index, direction === 'asc');
                });
            });
        }

        // // Add download button if .downloadable
        // if (table.classList.contains('downloadable')) {
        //     addDownloadButton(table);
        // }
    });
}

function sortTable(table, columnIndex, ascending = true) {
    const tbody = table.querySelector('tbody');
    if (!tbody) return;
    const rows = Array.from(tbody.rows);

    rows.sort((rowA, rowB) => {
        const cellA = rowA.cells[columnIndex] ? rowA.cells[columnIndex].innerText : '';
        const cellB = rowB.cells[columnIndex] ? rowB.cells[columnIndex].innerText : '';

        const valueA = isNaN(cellA) ? cellA.toLowerCase() : parseFloat(cellA);
        const valueB = isNaN(cellB) ? cellB.toLowerCase() : parseFloat(cellB);

        if (valueA < valueB) return ascending ? -1 : 1;
        if (valueA > valueB) return ascending ? 1 : -1;
        return 0;
    });

    rows.forEach(row => tbody.appendChild(row));
}

// function addDownloadButton(table) {
//     const downloadButton = document.createElement('button');
//     downloadButton.textContent = '💾 Download Data';
//     downloadButton.addEventListener('click', () => {
//         downloadCSV(table);
//     });

//     // Insert the button before the table or in some suitable location
//     table.parentNode.appendChild(downloadButton, table);
// }

// function downloadCSV(table) {
//     // Get headers from the thead
//     const tcaption = table.querySelector('caption');
//     const thead = table.querySelector('thead');
//     const tbody = table.querySelector('tbody');

//     if (!thead || !tbody) {
//         console.warn('Table is missing thead or tbody. Cannot create CSV.');
//         return;
//     }

//     const headerCells = thead.querySelectorAll('th');
//     const headers = Array.from(headerCells).map(th => cleanCSVValue(th.innerText));

//     const rows = Array.from(tbody.querySelectorAll('tr')).map(row => {
//         const cells = Array.from(row.querySelectorAll('td'));
//         return cells.map(td => cleanCSVValue(td.innerText));
//     });

//     // Combine headers and rows
//     const csvData = [headers].concat(rows);

//     // Convert to CSV string
//     const csvContent = csvData.map(rowArr => rowArr.join(',')).join('\n');

//     // Create a blob and trigger download
//     const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
//     const url = URL.createObjectURL(blob);

//     const link = document.createElement('a');
//     link.href = url;
    
//     // template string for filename:
//     // game name, date, table caption(if any), .csv
//     // fill spaces with underscores
    
//     let filename = document.getElementById('game_name').innerText;
//     if (tcaption) {
//         filename += '_' + tcaption.innerText;
//     }
//     filename += '_';
//     filename += new Date().toISOString().split('T')[0];
//     filename += '.csv';

//     filename = filename.replace(/ /g, '_');

//     link.download = filename;
//     document.body.appendChild(link);
//     link.click();
//     document.body.removeChild(link);
//     URL.revokeObjectURL(url);
// }

// // Clean CSV values by escaping double quotes and trimming whitespace
// function cleanCSVValue(value) {
//     const trimmed = value.trim();
//     // Escape double quotes by doubling them
//     const escaped = trimmed.replace(/"/g, '""');
//     // Wrap in quotes if it contains a comma or newline
//     if (escaped.search(/("|,|\n)/g) >= 0) {
//         return `"${escaped}"`;
//     }
//     return escaped;
// }

// Initial call
attachTableSortingAndDownloading();

// Observe DOM changes for newly added tables
const observer = new MutationObserver((mutationsList) => {
    for (const mutation of mutationsList) {
        if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
            attachTableSortingAndDownloading();
        }
    }
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});
