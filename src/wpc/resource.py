# Resource (ram and flash and stack) report
import gc
import os

import micropython

# from logger import logger_instance

# Log = logger_instance


def get_ram_usage(details):
    # gc.collect()
    free_ram = gc.mem_free()
    total_ram = free_ram + gc.mem_alloc()
    if details:
        print("RESOURCE: total ram=", total_ram)
    used_ram = total_ram - free_ram
    ram_usage_percent = (used_ram / total_ram) * 100
    return ram_usage_percent


def get_flash_usage(details):
    stats = os.statvfs("/")
    total_blocks = stats[2]
    free_blocks = stats[3]
    total_flash = total_blocks * stats[0]
    if details:
        print("RESOURCE: total flash=", total_flash)
    free_flash = free_blocks * stats[0]
    used_flash = total_flash - free_flash
    flash_usage_percent = (used_flash / total_flash) * 100
    return flash_usage_percent


def go(details=False):
    stack_usage = micropython.stack_use()
    if details:
        print("stack use", stack_usage)
    stack_percent = (stack_usage / 6144) * 100

    ram_usage_percent = get_ram_usage(details)
    flash_usage_percent = get_flash_usage(details)

    # if ram_usage_percent > 85 or flash_usage_percent > 85 or stack_percent > 85:
    #    Log.log(f"RESOURCE: RAM={ram_usage_percent:.0f}%, Flash={flash_usage_percent:.0f}%, Stack={stack_percent:.0f}%")

    print(f"RESOURCE: RAM={ram_usage_percent:.0f}%, Flash={flash_usage_percent:.0f}%, Stack={stack_percent:.0f}%")
