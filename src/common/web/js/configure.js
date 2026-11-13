async function build_game_config_select() {
  // get all configurations
  const response = await fetch("/api/game/configs_list");

  if (!response.status == 200) {
    console.error("Error fetching game configurations");
    return;
  }

  const data = await response.json(); // object {filename: {"name": "Game Name", "rom": "L2"}}

  // create mapping of key to "Game Name (rom)"
  const filename_to_name = {};
  for (const filename in data) {
    try {
      rom = data[filename].rom;
      // if the rom string is not a string with one or more characters, set it to NA
      if (typeof rom == "string" && rom.length > 0) {
        rom = `-${rom}`;
      } else {
        rom = "";
      }

      filename_to_name[filename] = `${data[filename].name} ${rom}`;
    } catch (error) {
      console.error(`Error parsing ${filename}: ${error}`);
    }
  }

  const game_config_select = await window.createDropDownElement(
    "game_config_select",
    "Select a game configuration",
    filename_to_name,
    (defaultValue = null),
    (sortOptions = true),
  );

  document
    .getElementById("game_config_select_placeholder")
    .replaceWith(game_config_select);

  // set currently active configuration as default
  const response_active = await fetch("/api/game/active_config");
  if (!response_active.status == 200) {
    console.error("Error fetching active game configuration");
    return;
  }

  const active_config = await response_active.json();
  const active_config_filename = active_config.active_config;

  // check if the active config is in the list of available configs
  if (active_config_filename in filename_to_name) {
    window.setDropDownValue(
      "game_config_select",
      active_config_filename,
      `${filename_to_name[active_config_filename]} (Current Setting)`,
    );
  } else {
    console.error(
      "Active configuration not in list of available configurations",
      active_config_filename,
    );
  }
}

// Dropdown value for "join a network that is not in the list"; can't collide with a
// real SSID because those are at most 32 bytes
const HIDDEN_NETWORK_OPTION = "__hidden_network_option_not_an_ssid__";

function show_hidden_ssid_input(show) {
  const input = document.querySelector('input[name="hidden_ssid"]');
  if (!input) return;
  input.hidden = !show;
  if (show) input.focus();
}

async function build_ssid_select() {
  // get list of wifi networks
  const response = await fetch("/api/available_ssids");
  const data = await response.json(); // list of [{'ssid':'wifi name', 'rssi': -50, 'configured': true}]

  // create mapping of ssid to "ssid + configured"
  const ssid_to_name = {};
  let configured_ssid = null;
  let configured_hidden = false;
  for (const ssid of data) {
    if (ssid.configured) {
      configured_ssid = ssid.ssid;
      // Saved network that the scan did not see (hidden, or out of range):
      // offer it in the manual field rather than as a scanned network
      if (ssid.hidden) {
        configured_hidden = true;
        continue;
      }
    }
    let name = ssid.ssid;
    if (ssid.configured) {
      name = `${name} (Current Setting)`;
    }
    ssid_to_name[ssid.ssid] = name;
  }
  ssid_to_name[HIDDEN_NETWORK_OPTION] = "Other (hidden network)...";

  const ssid_select = await window.createDropDownElement(
    "ssid_select",
    "Select a WiFi network",
    ssid_to_name,
    (defaultValue = null),
    (sortOptions = false),
    (optionsCallback = (value) =>
      show_hidden_ssid_input(value === HIDDEN_NETWORK_OPTION)),
  );

  document.getElementById("ssid_select_placeholder").replaceWith(ssid_select);

  // set configured ssid as default
  if (configured_hidden) {
    window.setDropDownValue(
      "ssid_select",
      HIDDEN_NETWORK_OPTION,
      ssid_to_name[HIDDEN_NETWORK_OPTION],
    );
    document.querySelector('input[name="hidden_ssid"]').value = configured_ssid;
    show_hidden_ssid_input(true);
  } else if (configured_ssid) {
    window.setDropDownValue(
      "ssid_select",
      configured_ssid,
      `${configured_ssid} (Current Setting)`,
    );
  }
}

// The SSID to save: the scanned network picked in the dropdown, or the name
// typed in for a hidden network. SSIDs can legally start or end with spaces,
// so the typed name is kept exactly as entered.
function selected_ssid() {
  const selected = window.getDropDownValue("ssid_select");
  if (selected === HIDDEN_NETWORK_OPTION) {
    return document.querySelector('input[name="hidden_ssid"]').value;
  }
  return selected;
}

async function populate_previous_ip() {
  const response = await window.smartFetch("/api/last_ip", null, false);
  if (!response.ok) {
    console.error("Error fetching previous IP");
    return;
  }
  const data = await response.json();
  const previous_ip = "http://" + data.ip;
  const ip_link = document.getElementById("previous-ip");
  ip_link.innerText = previous_ip;
  ip_link.href = previous_ip;
}

async function populate_configure_modal() {
  build_ssid_select();
  build_game_config_select();
  populate_previous_ip();
}

async function configure_check() {
  let response = await window.smartFetch("/api/in_ap_mode", null, false);
  if (!response.ok) {
    console.log("Retrying in AP mode check");
    response = await window.smartFetch("/api/in_ap_mode", null, false);
  }
  if (!response.ok) {
    console.error("Error checking AP mode status");
    return;
  }
  const data = await response.json();
  if (data.in_ap_mode) {
    await populate_configure_modal();
    // open the modal
    document.getElementById("configure_modal").setAttribute("open", "");
  }
}

configure_check();

async function set_vector_config() {
  // save the other configuration options
  const ssid = selected_ssid();
  const wifi_password = document.querySelector(
    'input[name="wifi_password"]',
  ).value;
  const vector_password = document.querySelector(
    'input[name="vector_password"]',
  ).value;
  const game_config = window.getDropDownValue("game_config_select");

  data = {
    ssid: ssid,
    wifi_password: wifi_password,
    vector_password: vector_password,
    game_config_filename: game_config,
  };

  // send a POST with the selected configuration
  // auth is not required because this route is only available in AP mode
  // the device reboots as soon as it saves, so a dropped connection means success
  try {
    return await window.smartFetch(
      "/api/settings/set_vector_config",
      (data = data),
      (auth = false),
      { timeoutMs: 8000 },
    );
  } catch (e) {
    console.log("Connection lost while saving, device is rebooting", e);
    return { status: 200, rebooted: true };
  }
}

// function to  save the configuration  and restart the device
async function save_configuration() {
  // save the vector configuration
  var replyDom = document.querySelector("#config-reply");
  var saveBtn = document.querySelector("#config-save-btn");
  saveBtn.disabled = true;
  var saveText = saveBtn.innerHTML;
  if (!selected_ssid()) {
    replyDom.innerHTML =
      "<p style='color:red;'>Select a WiFi network, or type in the name of a hidden one</p>";
    saveBtn.disabled = false;
    return;
  }
  saveBtn.innerHTML = "⏳ Saving...";
  let response_vector = await set_vector_config();
  saveBtn.disabled = false;
  saveBtn.innerHTML = saveText;
  if (response_vector.status !== 200) {
    replyDom.innerHTML =
      "<p style='color:red;'>Error saving vector configuration; Try again</p>";
    return;
  }

  response_vector = null;
  replyDom.innerHTML =
    "<p style='color:green;'>Configuration saved. Vector is rebooting to apply the changes. Make sure your reset clip is in place.</p>";
}

window.save_configuration = save_configuration;
