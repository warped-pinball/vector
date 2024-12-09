// modal
const modal = document.getElementById('configure_modal');

// // config values
// const vector_config_select = document.getElementById('vector_config');
// const vector_password_input = document.querySelector('input[name="vector_password"]');
// const WiFi_ssid_select = document.querySelector('select[name="WiFi_ssid"]');
// const WiFi_password_input = document.querySelector('input[name="WiFi_password"]');





async function populate_configure_modal() {
    // get json of all possible configurations
    const all_configs = JSON.parse(await window.fetchDecompress('/config/all.json.gz'));
    


    // list all keys in the json
    const filenames = Object.keys(all_configs)

    // create mapping of key to key/GameInfo/GameName
    const filename_to_name = {}
    for (const filename of filenames) {
        try {
            filename_to_name[filename] = all_configs[filename].GameInfo.GameName
        } catch (error) {
            console.error(`Error parsing ${filename}: ${error}`)
        }
    }

    // TODO currently active configuration as default
    const game_config_dropdown = window.createDropDownElement(
        'game_config_select', 
        'Select a game configuration', 
        filename_to_name
    )

    document.getElementById('game_config_placeholder').replaceWith(game_config_dropdown)

}



populate_configure_modal();















async function configure_check() {
    const response = await fetch('/api/in_ap_mode');
    const data = await response.json();
    if (data.in_ap_mode) {
        modal.setAttribute('open', ''); // Add the "open" attribute to the dialog
    }
}

configure_check();


// async function populate_configure_modal() {
//     // last IP?    
//     // get list of wifi networks
//     const response = await fetch('/api/available_ssids');
//     const data = await response.json();
//     WiFi_ssid_select.innerHTML = '';
//     for (const [ssid, rssi] of data) {
//         const option_element = document.createElement('option');
//         option_element.value = ssid;
//         option_element.innerText = ssid;
//         WiFi_ssid_select.appendChild(option_element);
//     }
// }

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