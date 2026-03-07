import SPI_DataStore as datastore
from logger import logger_instance

Log = logger_instance


CONFIG_VALUES = {
    "ssid": "Warped Pinball Network",
    "password": "pinkid1671",
    "Gpassword": "pinball",
}


def main():

    try:
        # Read existing configuration to preserve gamename and other fields
        existing = datastore.read_record("configuration")
        existing.update(CONFIG_VALUES)
        datastore.write_record("configuration", existing)
    except Exception as e:
        print("Failed to write configuration:", e)
        return

    # Read back and show
    config = datastore.read_record("configuration")

    print("Updated Configuration:")
    for k, v in config.items():
        print(f"{k}: {v}")

    # Show extras (unchanged)
    extras = datastore.read_record("extras")
    print("\nExtras (unchanged):")
    for k, v in extras.items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    main()
