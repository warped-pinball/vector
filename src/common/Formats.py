# This file is part of the Warped Pinball Vector Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0

"""
Game format mode management.

This module provides functions to retrieve and manage different game formats
(e.g., Standard, Practice, Golf, etc.) from game configuration files.
"""

import SharedState as S


def get_available_formats():
    """
    Retrieve available game formats from the current game configuration.

    Formats are defined in the game configuration JSON file under the "Formats" key.
    Each format can have optional configuration parameters for customization.

    Returns:
        list: List of format dictionaries, each containing:
            - id (int): Unique format identifier
            - name (str): Human-readable format name
            - description (str): Brief description of the format
            - options (dict, optional): Configuration options for the format
            - enable_function (callable or None): Function to enable the format

    """
    formats = []

    # Get formats from game configuration
    game_formats = S.gdata.get("Formats", {})

    # Default format is always available (Standard/Arcade mode)
    formats.append(
        {
            "id": 0,
            "name": "Standard",
            "description": "Manufacturer standard game play",
            "enable_function": None,
        }
    )

    # Add formats from game configuration
    format_id = 1
    for format_name, format_config in game_formats.items():
        if format_name == "Standard":
            continue  # Skip, already added as id 0

        format_entry = {
            "id": format_id,
            "name": format_name,
            "description": format_config.get("description", f"{format_name} mode"),
            "enable_function": None,
        }

        # Add options if they exist in the configuration
        if "options" in format_config:
            format_entry["options"] = format_config["options"]

        formats.append(format_entry)
        format_id += 1

    return formats


def get_format_by_id(format_id):
    """
    Get a specific format by its ID.

    Args:
        format_id (int): The format ID to retrieve

    Returns:
        dict or None: The format dictionary if found, None otherwise
    """
    formats = get_available_formats()
    return next((fmt for fmt in formats if fmt["id"] == format_id), None)


def get_format_by_name(format_name):
    """
    Get a specific format by its name.

    Args:
        format_name (str): The format name to retrieve

    Returns:
        dict or None: The format dictionary if found, None otherwise
    """
    formats = get_available_formats()
    return next((fmt for fmt in formats if fmt["name"] == format_name), None)
