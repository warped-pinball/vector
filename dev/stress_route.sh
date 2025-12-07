#!/bin/bash

# Usage: ./stress_test.sh <URL>

# Check if URL is provided
if [ -z "$1" ]; then
  echo "Usage: $0 <URL>"
  exit 1
fi

URL="$1"

# Initialize variables
concurrency=1
max_rps=0
max_concurrency=0

# Function to perform a single stress test iteration
stress_test() {
  local concurrent=$1
  local url=$2

  # Generate a list of requests
  seq 1 "$concurrent" | xargs -n1 -P "$concurrent" -I{} \
    curl -s -o /dev/null -w "%{http_code}\n" "$url"
}

echo "Starting stress test on $URL"

while true; do
  echo "Testing concurrency level: $concurrency"

  # Record start time
  start_time=$(date +%s.%N)

  # Perform stress test
  response_codes=$(stress_test "$concurrency" "$URL")

  # Record end time
  end_time=$(date +%s.%N)

  # Calculate elapsed time
  elapsed=$(echo "$end_time - $start_time" | bc)

  # Calculate Requests Per Second (RPS)
  if (( $(echo "$elapsed > 0" | bc -l) )); then
    rps=$(echo "$concurrency / $elapsed" | bc -l)
    rps=$(printf "%.2f" "$rps")
  else
    rps="Infinity"
  fi

  echo "Elapsed Time: $elapsed seconds"
  echo "Requests Per Second (RPS): $rps"

  # Check if all responses are 200
  non_200=$(echo "$response_codes" | grep -v "^200$" | wc -l)

  if [ "$non_200" -eq 0 ]; then
    # Update max values
    max_rps="$rps"
    max_concurrency="$concurrency"
    echo "All $concurrency requests succeeded with 200 OK."

    # Increment concurrency for next test
    concurrency=$((concurrency + 1))
  else
    echo "Encountered $non_200 non-200 responses. Stopping test."
    break
  fi

  echo "----------------------------------------"
done

echo "Stress Test Completed."
echo "Maximum Requests Per Second (RPS): $max_rps"
echo "Maximum Concurrency Level: $max_concurrency"
