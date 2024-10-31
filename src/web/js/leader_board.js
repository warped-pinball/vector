function updateLeaderboard() {
    const MIN_ROWS = 4;  // Minimum number of rows in the leaderboard
    const tableBody = document.getElementById('leaderboardTable').getElementsByTagName('tbody')[0];
    
    // TODO make 1st place oposite light/dark compared to rest of page
    
    // Function to create and populate a row
    function createRow(rank, initials = "", fullName = "", score = "", date = "") {
        let row = tableBody.insertRow();
        row.insertCell(0).innerText = rank;
        row.insertCell(1).innerText = score.toLocaleString ? score.toLocaleString() : score;
        row.insertCell(2).innerText = initials;
        row.insertCell(3).innerText = fullName;
        row.insertCell(4).innerText = date;

        if (rank === 1) {
            row.setAttribute("data-theme", "light");
        }
    }

    // Fetch leaderboard data
    fetch('/leaderboard')
        .then(response => response.json())
        .then(data => {
            tableBody.innerHTML = '';  // Clear existing rows

            // Populate table with fetched data
            data.forEach((player, index) => {
                createRow(index + 1, player.initials, player.full_name, Math.random() * 1000000, player.date);
            });

            // Add blank rows if less than MIN_ROWS are present
            for (let i = data.length; i < MIN_ROWS; i++) {
                createRow(i + 1);
            }
        })
        .catch(error => {
            console.error('Failed to load leaderboard data:', error);
        });
}

updateLeaderboard();
leaderboardIntervalId = setInterval(updateLeaderboard, 60000);


window.cleanup_leader_board = function() {
    clearInterval(leaderboardIntervalId);
    leaderboardIntervalId = null;
};