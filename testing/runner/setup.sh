# Create a folder
$ mkdir actions-runner && cd actions-runner
# Download the latest runner package
$ curl -o actions-runner-linux-arm64-2.322.0.tar.gz -L https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-linux-arm64-2.322.0.tar.gz
# Optional: Validate the hash
$ echo "a96b0cec7b0237ca5e4210982368c6f7d8c2ab1e5f6b2604c1ccede9cedcb143  actions-runner-linux-arm64-2.322.0.tar.gz" | shasum -a 256 -c
# Extract the installer
$ tar xzf ./actions-runner-linux-arm64-2.322.0.tar.gz


# ask the user for the token
echo "Please provide the token for the runner"
echo "You can get it from the repository settings -> Actions -> New Runner within the configuration script"
echo "https://github.com/warped-pinball/vector/settings/actions/runners/new?arch=arm64"

read -s token


# Create the runner and start the configuration experience
$ ./config.sh \
    --url https://github.com/warped-pinball/vector \
    --token $token \
    --labels pizero,hardware
# Last step, run it!
$ ./run.sh
