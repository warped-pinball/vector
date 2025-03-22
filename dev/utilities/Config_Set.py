import SPI_DataStore as datastore


def read_configuration():
    # Read the configuration record from storage
    config = datastore.read_record("configuration")
    extras = datastore.read_record("extras")
    return config, extras


def edit_configuration(config, extras):
    print("Current Configuration:")
    for key, value in reversed(list(config.items())):
        print(f"{key}: ({value})")

    print("\nEnter new values (type '-' to keep current value):")
    for key in reversed(list(config.keys())):
        new_value = input(f"{key} ({config[key]}): ").strip()
        if new_value != "-":  # Only update if new_value is not "-"
            config[key] = new_value

    print("\n\n\n\nCurrent EXTRAS:")
    for key, value in reversed(list(extras.items())):
        print(f"{key}: ({value})")

    print("\nEnter new values (type '-' to keep current value):")
    for key in reversed(list(extras.keys())):
        new_value = input(f"{key} ({extras[key]}): ").strip()
        if new_value != "-":  # Only update if new_value is not "-"
            if isinstance(extras[key], bool):
                if new_value.lower() in ["0", "false"]:
                    extras[key] = False
                elif new_value.lower() in ["1", "true"]:
                    extras[key] = True
                else:
                    print(f"Invalid input for boolean value: {new_value}. Keeping current value.")
            else:
                extras[key] = new_value

    return config, extras


def write_configuration(config, extras):
    # Write the updated configuration back to storage
    datastore.write_record("configuration", config)
    datastore.write_record("extras", extras)


def main():
    # Read current configuration
    config, extras = read_configuration()

    # Edit configuration
    #updated_config, updated_extras = edit_configuration(config, extras)

    config["ssid"] = "MoonShadow"
    config["password"] = "Pinbot43"
    config["gamename"] = "GameShow_LU4"
    config["Gpassword"] = ""

    extras["enable"] = 1
    extras["lastIP"] = "none"
    extras["message"] = " "
    extras["other"] = 1

    extras["tournament_mode"] = False
    extras["show_ip_address"] = True
    extras["messgae"] = " "
    extras["claim_scores"] = True
    extras["enter_intials_on_game"] = True
    extras["other"] = False

    for key, value in config.items():
        print(f"{key}: {value}")
    for key, value in extras.items():
        print(f"{key}: {value}")

    # Write updated configuration back to storage
    write_configuration(config, extras)

    config = datastore.read_record("configuration")
    # Display the updated configuration
    print("\nUpdated Configuration:")
    for key, value in config.items():
        print(f"{key}: {value}")

    extras = datastore.read_record("extras")
    print("\nExtras:")
    for key, value in extras.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
