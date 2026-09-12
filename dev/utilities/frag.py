# Utility to measure flash fragmentation
#   some conern that active3 flash log files with user files could fill space

import os


def measure_fragmentation():
    # Get filesystem stats
    fs_stat = os.statvfs("/")
    total_blocks = fs_stat[2]  # f_blocks
    block_size = fs_stat[0]  # f_frsize
    free_blocks = fs_stat[3]  # f_bfree

    used_blocks = total_blocks - free_blocks
    total_space = total_blocks * block_size
    free_space = free_blocks * block_size
    used_space = used_blocks * block_size

    # Create a mock of free block sizes, assuming all free space is fragmented into minimum size blocks
    # This is a simplification, as actually determining free block sizes would require direct access to the filesystem
    num_free_blocks = free_blocks
    avg_free_block_size = free_space / num_free_blocks if num_free_blocks > 0 else 0

    fragmentation_index = (num_free_blocks * avg_free_block_size) / free_space if free_space > 0 else 0

    print(f"Total space: {total_space / 1024} KB")
    print(f"Used space: {used_space / 1024} KB")
    print(f"Free space: {free_space / 1024} KB")
    print(f"Number of free blocks: {num_free_blocks}")
    print(f"Average free block size: {avg_free_block_size / 1024} KB")
    print(f"Fragmentation index: {fragmentation_index}")


measure_fragmentation()
