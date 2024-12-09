// modal
const modal = document.getElementById('configure_modal');

// // config values
// const vector_config_select = document.getElementById('vector_config');
// const vector_password_input = document.querySelector('input[name="vector_password"]');
// const WiFi_ssid_select = document.querySelector('select[name="WiFi_ssid"]');
// const WiFi_password_input = document.querySelector('input[name="WiFi_password"]');






async function populate_configure_modal() {
    // get list of game configs
    const response = await fetch('/api/game/list_games');
    const games = await response.json();
    const vector_config_select = document.getElementById('vector_config');


    // get list of wifi networks
    const response = await fetch('/api/available_ssids');
    const data = await response.json();

}



















async function configure_check() {
    const response = await fetch('/api/in_ap_mode');
    const data = await response.json();
    if (data.in_ap_mode) {
        modal.setAttribute('open', ''); // Add the "open" attribute to the dialog
    }
}

configure_check();


async function populate_configure_modal() {
    // last IP?
    
    // TODO figure out the currently active configuration if any and select that in the dropdowns
    // get list of game configs
    const response2 = await fetch('/api/game/list_games');
    const data2 = await response2.json();
    vector_config_select.innerHTML = '';    
    for (const game of data2) {
        const option_element = document.createElement('option');
        option_element.value = game;
        option_element.innerText = game;
        vector_config_select.appendChild(option_element);
    }
    
    // get list of wifi networks
    const response = await fetch('/api/available_ssids');
    const data = await response.json();
    WiFi_ssid_select.innerHTML = '';
    for (const [ssid, rssi] of data) {
        const option_element = document.createElement('option');
        option_element.value = ssid;
        option_element.innerText = ssid;
        WiFi_ssid_select.appendChild(option_element);
    }
}

// populate_configure_modal();

// function to  save the configuration  and restart the device
async function save_configuration() {
    const config = {
        ssid: WiFi_ssid_select.value,
        password: WiFi_password_input.value,
        game: vector_config_select.value,
        game_password: vector_password_input.value
    }
    const response = await fetch('/api/configure', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(config)
    });
}