function updateLeaderboard() {
    const MIN_ROWS = 4;  // Minimum number of rows in the leaderboard
    const tableBody = document.getElementById('leaderboardTable').getElementsByTagName('tbody')[0];

    // Function to create and populate a row
    function createRow(rank, initials = "", fullName = "", score = "", date = "") {
        let row = tableBody.insertRow();
        row.insertCell(0).innerHTML = rank;
        row.insertCell(1).innerHTML = initials;
        row.insertCell(2).innerHTML = fullName;
        row.insertCell(3).innerHTML = score.toLocaleString ? score.toLocaleString() : score;
        row.insertCell(4).innerHTML = date;
    }

    // Fetch leaderboard data
    fetch('/leaderboard')
        .then(response => response.json())
        .then(data => {
            tableBody.innerHTML = '';  // Clear existing rows

            // Populate table with fetched data
            data.forEach((player, index) => {
                createRow(index + 1, player.initials, player.full_name, player.score, player.date);
            });

            // Add blank rows if less than MIN_ROWS are present
            for (let i = data.length; i < MIN_ROWS; i++) {
                createRow(i + 1);
            }
        })
        .catch(error => {
            console.error('Failed to load leaderboard data:', error);
            // Fill table with minimum blank rows if fetch fails
            tableBody.innerHTML = '';
            for (let i = 0; i < MIN_ROWS; i++) {
                createRow(i + 1);
            }
        });
}

updateLeaderboard();
setInterval(updateLeaderboard, 60000);