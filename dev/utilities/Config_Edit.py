import SPI_DataStore as datastore


def read_configuration():
    # Read the configuration record from storage
    config = datastore.read_record("configuration")
    return config


def edit_configuration(config):
    print("Current Configuration:")
    for key, value in reversed(list(config.items())):
        print(f"{key}: ({value})")

    print("\nEnter new values (type '-' to keep current value):")
    for key in reversed(list(config.keys())):
        new_value = input(f"{key} ({config[key]}): ").strip()
        if new_value != "-":  # Only update if new_value is not "-"
            config[key] = new_value

    return config


def write_configuration(config):
    # Write the updated configuration back to storage
    datastore.write_record("configuration", config)


def main():
    # Read current configuration
    config = read_configuration()

    # Edit configuration
    updated_config = edit_configuration(config)

    # Write updated configuration back to storage
    write_configuration(updated_config)

    # Display the updated configuration
    print("\nUpdated Configuration:")
    for key, value in updated_config.items():
        print(f"{key}: {value}")

    extras = datastore.read_record("extras")
    print("\nExtras:")
    for key, value in extras.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
