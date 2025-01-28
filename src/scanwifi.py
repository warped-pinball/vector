# This file is part of the Warped Pinball SYS11Wifi Project.
import network as networkSc


def scan_wifi2():
    wlan = networkSc.WLAN(networkSc.STA_IF)
    wlan.active(True)

    # Scan for networks
    networks = wlan.scan()

    output = {}
    for net in networks:
        ssid = net[0].decode("utf-8").strip()  # SSID
        rssi = net[3]
        if ssid:
            if ssid not in output or rssi > output[ssid]["rssi"]:
                output[ssid] = {"ssid": ssid, "rssi": rssi}

    wlan.active(False)  # Deactivate the interface

    return sorted(list(output.values()), key=lambda x: x["rssi"], reverse=True)


if __name__ == "__main__":
    sorted_networks = scan_wifi2()
    print("Unique SSIDs in the area (sorted by RSSI):")
    for network in sorted_networks:
        ssid = network["ssid"]
        rssi = network["rssi"]
        print(f"SSID: {ssid}, RSSI: {rssi}")
