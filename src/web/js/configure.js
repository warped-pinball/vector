

async function build_game_config_select(){
    // get all configurations    
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
    const game_config_select = await window.createDropDownElement(
        'game_config_select', 
        'Select a game configuration', 
        filename_to_name
    )

    document.getElementById('game_config_select_placeholder').replaceWith(game_config_select)
}

async function build_ssid_select(){
    // get list of wifi networks
    const response = await fetch('/api/available_ssids');
    const data = await response.json(); // list of [ssid, rssi]

    const ssid_select = await window.createDropDownElement(
        'ssid_select',
        'Select a WiFi network',
        data.map(([ssid, rssi]) => ssid)
    )

    document.getElementById('ssid_select_placeholder').replaceWith(ssid_select)
}

async function populate_configure_modal() {
    await build_game_config_select();
    await build_ssid_select();
}

// modal
const modal = document.getElementById('configure_modal');

async function configure_check() {
    const response = await fetch('/api/in_ap_mode');
    const data = await response.json();
    if (data.in_ap_mode) {
        await populate_configure_modal();
        modal.setAttribute('open', ''); // Add the "open" attribute to the dialog
    }
}

configure_check();

// function to  save the configuration  and restart the device
async function save_configuration() {
    // get the selected configuration
    const selected_config = window.getDropDownValue('game_config_select');
    
    // get all configurations (this will likely be cached)
    const all_configs = JSON.parse(await window.fetchDecompress('/config/all.json.gz'));
    const config = all_configs[selected_config];

    console.log('Selected configuration:', selected_config);
    console.log('Configuration:', config);

    // send a POST with the selected configuration
    // auth is not required because this route is only available in AP mode
    const response = await window.smartFetch('no_password', '/api/game/set_config', data = config, auth=false);

    // check if the response is ok
    if (!response.ok) {
        alert('Error saving configuration try again');
        return;
    }

    alert('Configuration saved, please power cycle your Pinball Machine to apply the changes');
}

window.save_configuration = save_configuration;