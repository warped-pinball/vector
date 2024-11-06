from network import WLAN, AP_IF, STA_IF
import ssl
from microdot import Microdot, Response
import uasyncio as asyncio
import usocket
import select
import json
import time

app = Microdot()

# Global variable to store scanned networks
scanned_networks = []

# Function to scan networks once
def scan_networks():
    global scanned_networks
    wlan = WLAN(STA_IF)
    wlan.active(True)
    print("Scanning for available networks...")
    networks = wlan.scan()
    print(f"Found {len(networks)} networks")
    ssid_rssi_list = {}
    for net in networks:
        ssid = net[0].decode('utf-8').strip()  # SSID
        rssi = net[3]
        if ssid:
            if ssid in ssid_rssi_list:
                ssid_rssi_list[ssid] = max(rssi, ssid_rssi_list[ssid])
            else:
                ssid_rssi_list[ssid] = rssi

    # Sort by RSSI from highest to lowest
    sorted_networks = sorted(ssid_rssi_list.items(), key=lambda x: x[1], reverse=True)
    print("Available networks sorted by signal strength:")
    for ssid, rssi in sorted_networks:
        print(f"  {ssid}: {rssi} dBm")

    # Update the global scanned_networks variable
    scanned_networks = [{'ssid': ssid, 'rssi': rssi} for ssid, rssi in sorted_networks]

# New route to provide network list in JSON format
@app.route('/networks')
async def networks(request):
    print("Serving network list")
    if scanned_networks:
        networks_json = scanned_networks
    else:
        networks_json = [{'ssid': 'No networks found', 'rssi': ''}]
    return Response(body=json.dumps(networks_json), headers={'Content-Type': 'application/json'})

# Landing page route
@app.route('/')
async def index(request):
    print("Serving landing page")
    # Serve the HTML page without scanning networks
    html = """
    <html>
        <head>
            <title>Captive Portal</title>
            <meta charset="UTF-8">
            <script>
                async function loadNetworks() {
                    try {
                        const response = await fetch('/networks');
                        if (response.ok) {
                            const networks = await response.json();
                            const list = document.getElementById('network-list');
                            list.innerHTML = '';
                            networks.forEach(function(network) {
                                const li = document.createElement('li');
                                li.textContent = network.ssid + (network.rssi ? ' (Signal: ' + network.rssi + ' dBm)' : '');
                                list.appendChild(li);
                            });
                        } else {
                            console.error('Network response was not ok.');
                        }
                    } catch (error) {
                        console.error('Fetch error:', error);
                    }
                }

                window.onload = function() {
                    loadNetworks();
                };
            </script>
        </head>
        <body>
            <h1>Available Wi-Fi Networks</h1>
            <ul id="network-list">
                <li>Loading networks...</li>
            </ul>
        </body>
    </html>
    """
    return Response(body=html, headers={'Content-Type': 'text/html'})


# Start the access point and servers
def start_web():
    # Initialize the access point interface
    wlan = WLAN(STA_IF)
    wlan.active(True)
    wlan.connect(
        'oaisjdoaijdoisd',
        'hdiauhdiushdiuahsd'
    )
    print("Connecting to WiFi...")
    ttl = 4
    while wlan.isconnected() == False:
        if ttl == 0:
            break
        time.sleep(1)
        ttl -= 1
    if wlan.isconnected():
        print("Connected to WiFi")
    else:
        print("Failed to connect to WiFi")
        return
    # Retrieve the IP address
    ip_address = wlan.ifconfig()[0]
    print("IP address:", ip_address)

    async def run_servers():
        print("Starting servers...")
        loop = asyncio.get_event_loop()

        sslctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        sslctx.load_cert_chain('/certs/cert.der', '/certs/key.der')

        loop.create_task(app.start_server(host='0.0.0.0', port=443, ssl=sslctx))
        print("> HTTP server started on port 443")

        # Keep the loop running
        while True:
            await asyncio.sleep(0.1)  # Yield control frequently

    # Run servers concurrently
    asyncio.run(run_servers())

# Start the access point and servers
start_web()
