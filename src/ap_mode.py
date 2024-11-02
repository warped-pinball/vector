from network import WLAN, AP_IF, STA_IF
from microdot import Microdot, Response
import uasyncio as asyncio
import usocket
import select
import json

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

# Connectivity check routes
@app.route('/generate_204')
@app.route('/hotspot-detect.html')
@app.route('/connectivity-check.html')
@app.route('/success.txt')
async def connectivity_check(request):
    # Redirect to captive portal landing page
    print(f"Connectivity check for {request.path}, redirecting to '/'")
    return Response.redirect('/')

# DNS server handler
async def dns_handler(socket, ip_address):
    print("DNS handler started")
    while True:
        try:
            r, w, e = select.select([socket], [], [], 0)
            if socket in r:
                request_data, client = socket.recvfrom(512)
                print(f"Received DNS request from {client}")
                # Process DNS request
                response = request_data[:2]  # request id
                response += b"\x81\x80"  # response flags
                response += request_data[4:6] + request_data[4:6]  # qd/an count
                response += b"\x00\x00\x00\x00"  # ns/ar count
                response += request_data[12:]  # original request body
                response += b"\xC0\x0C"  # pointer to domain name at byte 12
                response += b"\x00\x01\x00\x01"  # type and class (A record / IN class)
                response += b"\x00\x00\x00\x3C"  # time to live 60 seconds
                response += b"\x00\x04"  # response length (4 bytes = 1 ipv4 address)
                response += bytes(map(int, ip_address.split(".")))  # ip address parts
                socket.sendto(response, client)
                print(f"DNS response sent to {client}")
            await asyncio.sleep(0)  # Yield control
        except Exception as e:
            print("DNS handler error: {}".format(e))
            await asyncio.sleep(0)

# Start the access point and servers
def start_ap():
    # Initialize the access point interface
    ap = WLAN(AP_IF)
    ap.config(essid='Warped Pinball', security=0)
    ap.active(True)
    print("Access point 'Warped Pinball' started")

    # Retrieve the AP's IP address
    ip_address = ap.ifconfig()[0]
    print(f"AP IP address: {ip_address}")

    # Scan networks once
    scan_networks()

    async def run_servers():
        print("Starting servers...")
        # Start DNS server
        _socket = usocket.socket(usocket.AF_INET, usocket.SOCK_DGRAM)
        _socket.setblocking(False)
        _socket.setsockopt(usocket.SOL_SOCKET, usocket.SO_REUSEADDR, 1)
        _socket.bind(("0.0.0.0", 53))
        print("> DNS server started on port 53")

        loop = asyncio.get_event_loop()
        loop.create_task(dns_handler(_socket, ip_address))
        loop.create_task(app.start_server(host='0.0.0.0', port=80))
        print("> HTTP server started on port 80")

        # Keep the loop running
        while True:
            await asyncio.sleep(0.1)  # Yield control frequently

    # Run servers concurrently
    asyncio.run(run_servers())

# Start the access point and servers
start_ap()
