# Resource (ram and flash) report
import gc
import os

call_count = 0

def get_ram_usage():
    global call_count
    call_count += 1
    # Run garbage collector to free up memory
    gc.collect()
    free_ram = gc.mem_free()
    total_ram = free_ram + gc.mem_alloc()
    if call_count < 3:
        print("RESOURCE: total ram= ", total_ram)
    used_ram = total_ram - free_ram
    ram_usage_percent = (used_ram / total_ram) * 100
    return ram_usage_percent

def get_flash_usage():
    global call_count
    stats = os.statvfs("/")
    total_blocks = stats[2]
    free_blocks = stats[3]
    total_flash = total_blocks * stats[0]
    if call_count < 3:
        print("RESOURCE: total flash= ", total_flash)
    free_flash = free_blocks * stats[0]
    used_flash = total_flash - free_flash
    flash_usage_percent = (used_flash / total_flash) * 100
    return flash_usage_percent

def go():   
    # Calculate RAM and Flash usage
    ram_usage_percent = get_ram_usage()
    flash_usage_percent = get_flash_usage()
    print(f"RESOURCE: RAM= {ram_usage_percent:.2f}% full, Flash: {flash_usage_percent:.2f}% full")    

if __name__ == "__main__":
    go()
