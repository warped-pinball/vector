
async function build_game_config_select(){
    // get all configurations
    const response = await fetch('/api/game/configs_list');

    if (!response.status == 200) {
        console.error('Error fetching game configurations');
        return;
    }

    const data = await response.json(); // object {filename: {"name": "Game Name", "rom": "L2"}}

    // create mapping of key to "Game Name (rom)"
    const filename_to_name = {}
    for (const filename in data) {
        try {
            rom = data[filename].rom;
            // if the rom string is not a string with one or more characters, set it to NA
            if (typeof rom == 'string' && rom.length > 0) {
                rom = `-${rom}`;
            } else {
                rom = '';
            }

            filename_to_name[filename] = `${data[filename].name} ${rom}`;
        } catch (error) {
            console.error(`Error parsing ${filename}: ${error}`)
        }
    }

    const game_config_select = await window.createDropDownElement(
        'game_config_select',
        'Select a game configuration',
        filename_to_name,
        defaultValue=null,
        sortOptions=true
    )

    document.getElementById('game_config_select_placeholder').replaceWith(game_config_select)

    // set currently active configuration as default
    const response_active = await fetch('/api/game/active_config');
    if (!response_active.status == 200) {
        console.error('Error fetching active game configuration');
        return;
    }

    const active_config = await response_active.json();
    const active_config_filename = active_config.active_config;

    // check if the active config is in the list of available configs
    if (active_config_filename in filename_to_name) {
        window.setDropDownValue('game_config_select', active_config_filename, `${filename_to_name[active_config_filename]} (Current Setting)`);
    } else {
        console.error('Active configuration not in list of available configurations', active_config_filename);
    }

}

async function build_ssid_select(){
    // get list of wifi networks
    const response = await fetch('/api/available_ssids');
    const data = await response.json(); // list of [{'ssid':'wifi name', 'rssi': -50, 'configured': true}]

    // create mapping of ssid to "ssid + configured"
    const ssid_to_name = {}
    for (const ssid of data) {
        let name = ssid.ssid;
        if (ssid.configured) {
            name = `${name} (Current Setting)`;
            configured_ssid = ssid.ssid;
        }
        ssid_to_name[ssid.ssid] = name;
    }

    const ssid_select = await window.createDropDownElement(
        'ssid_select',
        'Select a WiFi network',
        ssid_to_name,
        defaultValue=null,
        sortOptions=false
    )

    document.getElementById('ssid_select_placeholder').replaceWith(ssid_select)

    // set configured ssid as default
    if (configured_ssid) {
        window.setDropDownValue('ssid_select', configured_ssid, `${configured_ssid} (Current Setting)`);
    }


}

async function populate_previous_ip() {
    const response = await window.smartFetch('/api/last_ip', null, false);
    if (!response.ok) {
        console.error('Error fetching previous IP');
        return;
    }
    const data = await response.json();
    const previous_ip = "http://" + data.ip;
    const ip_link = document.getElementById('previous-ip');
    ip_link.innerText = previous_ip;
    ip_link.href = previous_ip;
}


async function populate_configure_modal() {
    build_ssid_select();
    build_game_config_select();
    populate_previous_ip();
}

async function configure_check() {
    let response = await window.smartFetch('/api/in_ap_mode', null, false);
    if (!response.ok) {
        console.log('Retrying in AP mode check');
        response = await window.smartFetch('/api/in_ap_mode', null, false);
    }
    if (!response.ok) {
        console.error('Error checking AP mode status');
        return;
    }
    const data = await response.json();
    if (data.in_ap_mode) {
        await populate_configure_modal();
        // open the modal
        document.getElementById('configure_modal').setAttribute('open', '');
    }
}

configure_check();


async function set_vector_config() {
    // save the other configuration options
    // ssid select
    const ssid = window.getDropDownValue('ssid_select');
    const wifi_password = document.querySelector('input[name="wifi_password"]').value;
    const vector_password = document.querySelector('input[name="vector_password"]').value;
    const game_config = window.getDropDownValue('game_config_select');

    data = {
        ssid: ssid,
        wifi_password: wifi_password,
        vector_password: vector_password,
        game_config_filename: game_config
    }

    // send a POST with the selected configuration
    // auth is not required because this route is only available in AP mode
    const response = await window.smartFetch('/api/settings/set_vector_config', data = data, auth=false);
    return response;
}

// function to  save the configuration  and restart the device
async function save_configuration() {
    // save the vector configuration
    let response_vector = await set_vector_config();

    if (!response_vector.status == 200) {
        alert('Error saving vector configuration; Try again');
        return;
    }

    response_vector = null;

    alert('Configuration saved. Power cycle your Pinball Machine to apply the changes');
}

window.save_configuration = save_configuration;
