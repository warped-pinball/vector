# This file is part of the Warped Pinball SYS11Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""
   Memory interface main

   start hardware PIO/DMA memory interfaces
"""
import json

import machine
import Ram_Intercept as RamInt
import SPI_Store as fram
import uctypes
from displayMessage import fixAdjustmentChecksum
from logger import logger_instance

Log = logger_instance
from Shadow_Ram_Definitions import SRAM_DATA_BASE, SRAM_DATA_LENGTH, shadowRam

ram_access = uctypes.bytearray_at(SRAM_DATA_BASE, SRAM_DATA_LENGTH)


def go():
    # A_Select pin initializtion
    a_select = machine.Pin(27, machine.Pin.OUT)
    a_select.value(0)

    a_datdir = machine.Pin(28, machine.Pin.OUT)
    a_datdir.value(0)

    # Restore ram values from Serial FRAM
    fram.Restore_Mem(shadowRam, SRAM_DATA_LENGTH)
    print("MEM: SRAM Restored")

    print("MEM: checksum")
    if not fixAdjustmentChecksum():
        Log.log("MEM: Checksum correction")

    # Boot up PIO/DMA Ram Intercept system
    r = RamInt.configure()
    if r is "fault":
        Log.log("MEM: Ram Intercept Fault - cycle power")
        while True:
            pass


# Function to save the machine ram to a JSON file
def save_ram():
    try:
        data_list = list(ram_access)  # Convert bytearray to list of integers
        with open("ramImage_new.json", "w") as file:
            json.dump(data_list, file)
        Log.log("MEM: Data saved to file successfully")
    except Exception as e:
        Log.log("MEM: Failed to save data to file: ", e)


# Function to restore RAM from JSON
def restore_ram():
    try:
        with open("ramImage_new.json", "r") as file:
            data_list = json.load(file)  # Deserialize JSON content to a list of integers
        # Ensure the bytearray can hold the data from the file
        if len(data_list) <= len(ram_access):
            for i, value in enumerate(data_list):
                ram_access[i] = value
            Log.log("MEM: Data restored from file successfully")
        else:
            Log.log("MEM: Restore from file size problem")
    except Exception:
        Log.log("MEM: Failed to restore data from file: ")


def reset():
    restore_ram()
    fram.write_all_fram_now()


def blank_ram():
    # blank the entire ram_access buffer rather than a fixed 2048 bytes
    for i in range(len(ram_access)):
        ram_access[i] = 0
