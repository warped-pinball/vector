# import Memory_Main
import SPI_DataStore as datastore
import SPI_Store
from logger import logger_instance

Log = logger_instance


CONFIG_VALUES = {
    "ssid": "MoonShadow",
    "gamename": "Pinbot_V2",
    "password": "Pinbot43",
    "Gpassword": "",
}

EXTRAS_VALUES = {
    "enter_initials_on_game": True,
    "claim_scores": True,
    "message": "ok",
    "show_ip_address": True,
    "tournament_mode": False,
    "lastIP": "none",
    "flag5": False,
    "flag6": False,
    "other": 1,
}


def clear():
    datastore.blankAll()

    print("\nConfiguration Cleared:")
    config = datastore.read_record("configuration")
    for key, value in config.items():
        print(f"{key}: {value}")
    print("\n")
    extras = datastore.read_record("extras")
    for key, value in extras.items():
        print(f"{key}: {value}")

    # Memory_Main.blank_ram()
    # SPI_Store.write_all_fram_now()


def main():
    clear()

    try:
        datastore.write_record("configuration", CONFIG_VALUES)
        datastore.write_record("extras", EXTRAS_VALUES)
    except Exception as e:
        print("Failed to write configuration:", e)
        return

    # Read back and show
    config = datastore.read_record("configuration")
    extras = datastore.read_record("extras")

    print("Updated Configuration:")
    for k, v in config.items():
        print(f"{k}: {v}")

    print("\nExtras:")
    for k, v in extras.items():
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
