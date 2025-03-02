# clear wifi and game selection configuration out
import Memory_Main

import SPI_DataStore as datastore
import SPI_Store
from logger import logger_instance

Log = logger_instance


def main():
    datastore.blankAll()

    Log.delete_log()

    """
    config = datastore.read_record("configuration")
    config["ssid"]=""
    config["password"]=""
    config["gamename"]="GenericSystem11"
    config["Gpassword"]=""
    datastore.write_record("configuration", config)

    extras = datastore.read_record("extras")
    print("extras before",extras)
    extras["enable"]=1
    extras["lastIP"]=""
    extras["message"]=""
    extras["other"]=1
    datastore.write_record("extras", extras)
    print("extras->",extras)
    """

    print("\nConfiguration Cleared:")
    config = datastore.read_record("configuration")
    for key, value in config.items():
        print(f"{key}: {value}")
    print("\n")
    extras = datastore.read_record("extras")
    for key, value in extras.items():
        print(f"{key}: {value}")

    Memory_Main.blank_ram()
    SPI_Store.write_all_fram_now()


if __name__ == "__main__":
    main()
