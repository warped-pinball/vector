# This file is part of the Warped Pinball SYS11Wifi Project.
import network as networkSc

def scan_wifi2():
    wlan = networkSc.WLAN(networkSc.STA_IF)
    wlan.active(True)
    
    # Scan for networks
    networks = wlan.scan()

    ssid_rssi_list = []
    for net in networks:
        ssid = net[0].decode('utf-8').strip()  #SSID
        rssi = net[3]  
        if ssid:
            ssid_rssi_list.append((ssid, rssi))  # Store SSID and RSSI

    wlan.active(False)  # Deactivate the interface
    # Remove duplicates
    ssid_rssi_dict = {ssid: rssi for ssid, rssi in ssid_rssi_list}

    #sort by RSSI from highest to lowest
    sorted_ssid_rssi = sorted(ssid_rssi_dict.items(), key=lambda x: x[1], reverse=True)

    return sorted_ssid_rssi

if __name__ == "__main__":
    sorted_networks = scan_wifi2()
    print("Unique SSIDs in the area (sorted by RSSI):")
    for ssid, rssi in sorted_networks:
        print(f"SSID: {ssid}, RSSI: {rssi}")


