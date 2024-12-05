#!/usr/bin/env python3

import os
import math
import argparse

def find_worst_offenders(directory, block_size=4096):
    """
    Recursively walks through a directory to find small files and inefficient files
    based on filesystem block size constraints.

    Parameters:
    - directory (str): The path to the directory to analyze.
    - block_size (int): The filesystem block size in bytes (default is 4096).

    Returns:
    - A tuple containing two lists: small_files and inefficient_files.
    """
    small_files = []
    inefficient_files = []
    for root, dirs, files in os.walk(directory):
        for name in files:
            filepath = os.path.join(root, name)
            try:
                size = os.path.getsize(filepath)
            except OSError:
                continue  # Skip files that cannot be accessed

            if size < block_size:
                # Small files (less than one block)
                wasted_space = block_size - size
                wasted_percentage = (wasted_space / block_size) * 100
                small_files.append({
                    'path': filepath,
                    'size': size,
                    'wasted_space': wasted_space,
                    'wasted_percentage': wasted_percentage
                })
            else:
                # Inefficient files (size >= one block)
                bytes_over_block = size % block_size
                if bytes_over_block == 0:
                    # Perfectly fits into blocks, no wasted space
                    continue
                else:
                    num_blocks = math.ceil(size / block_size)
                    actual_space = num_blocks * block_size
                    wasted_space = actual_space - size
                    wasted_percentage = (wasted_space / actual_space) * 100
                    inefficient_files.append({
                        'path': filepath,
                        'size': size,
                        'bytes_over_block': bytes_over_block,
                        'wasted_space': wasted_space,
                        'wasted_percentage': wasted_percentage,
                        'num_blocks': num_blocks
                    })

    # Sort small files by wasted space descending
    small_files.sort(key=lambda x: x['wasted_space'], reverse=True)
    # Sort inefficient files by bytes over block ascending
    inefficient_files.sort(key=lambda x: x['bytes_over_block'])

    return small_files, inefficient_files

def format_size(size):
    """Helper function to format the size in bytes into a human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def main():
    parser = argparse.ArgumentParser(
        description='Find files that are inefficiently using disk space due to filesystem block size constraints.'
    )
    parser.add_argument('directory', help='The path to the directory to analyze')
    parser.add_argument('-b', '--block-size', type=int, default=4096,
                        help='Filesystem block size in bytes (default: 4096)')
    parser.add_argument('-n', '--no-format', action='store_true',
                        help='Do not format sizes into human-readable units')
    parser.add_argument('-l', '--limit', type=int, default=None,
                        help='Limit the output to N files per category')
    args = parser.parse_args()

    small_files, inefficient_files = find_worst_offenders(
        args.directory,
        block_size=args.block_size
    )

    if not args.no_format:
        # Format sizes into human-readable units
        for f in small_files:
            f['size_str'] = format_size(f['size'])
            f['wasted_space_str'] = format_size(f['wasted_space'])
        for f in inefficient_files:
            f['size_str'] = format_size(f['size'])
            f['wasted_space_str'] = format_size(f['wasted_space'])
            f['bytes_over_block_str'] = format_size(f['bytes_over_block'])
    else:
        # Use raw sizes in bytes
        for f in small_files:
            f['size_str'] = f"{f['size']} B"
            f['wasted_space_str'] = f"{f['wasted_space']} B"
        for f in inefficient_files:
            f['size_str'] = f"{f['size']} B"
            f['wasted_space_str'] = f"{f['wasted_space']} B"
            f['bytes_over_block_str'] = f"{f['bytes_over_block']} B"

    # Prepare headers
    headers_small_files = ["Size", "Loss", "% Loss", "Path"]
    headers_inefficient_files = ["Size", "Bytes Over Block", "Loss", "% Loss", "Path"]

    # Output the results
    def print_small_files(files_list):
        # Calculate column widths
        size_width = max(len(headers_small_files[0]), max((len(f['size_str']) for f in files_list), default=0))
        loss_width = max(len(headers_small_files[1]), max((len(f['wasted_space_str']) for f in files_list), default=0))
        percent_width = max(len(headers_small_files[2]), max((len(f"{f['wasted_percentage']:.2f}%") for f in files_list), default=0))

        # Print header
        print(f"{headers_small_files[0]:<{size_width}} {headers_small_files[1]:<{loss_width}} {headers_small_files[2]:<{percent_width}} {headers_small_files[3]}")
        # Print separator
        print(f"{'-'*size_width} {'-'*loss_width} {'-'*percent_width} {'-'*len(headers_small_files[3])}")

        # Print each file
        for f in files_list[:args.limit]:
            size_str = f['size_str']
            loss_str = f['wasted_space_str']
            percent_str = f"{f['wasted_percentage']:.2f}%"
            print(f"{size_str:<{size_width}} {loss_str:<{loss_width}} {percent_str:<{percent_width}} {f['path']}")

    def print_inefficient_files(files_list):
        # Calculate column widths
        size_width = max(len(headers_inefficient_files[0]), max((len(f['size_str']) for f in files_list), default=0))
        over_block_width = max(len(headers_inefficient_files[1]), max((len(f['bytes_over_block_str']) for f in files_list), default=0))
        loss_width = max(len(headers_inefficient_files[2]), max((len(f['wasted_space_str']) for f in files_list), default=0))
        percent_width = max(len(headers_inefficient_files[3]), max((len(f"{f['wasted_percentage']:.2f}%") for f in files_list), default=0))

        # Print header
        print(f"{headers_inefficient_files[0]:<{size_width}} {headers_inefficient_files[1]:<{over_block_width}} {headers_inefficient_files[2]:<{loss_width}} {headers_inefficient_files[3]:<{percent_width}} {headers_inefficient_files[4]}")
        # Print separator
        print(f"{'-'*size_width} {'-'*over_block_width} {'-'*loss_width} {'-'*percent_width} {'-'*len(headers_inefficient_files[4])}")

        # Print each file
        for f in files_list[:args.limit]:
            size_str = f['size_str']
            over_block_str = f['bytes_over_block_str']
            loss_str = f['wasted_space_str']
            percent_str = f"{f['wasted_percentage']:.2f}%"
            print(f"{size_str:<{size_width}} {over_block_str:<{over_block_width}} {loss_str:<{loss_width}} {percent_str:<{percent_width}} {f['path']}")

    print("\n===== Small Files (< 1 Block) =====")
    if small_files:
        print_small_files(small_files)
    else:
        print("No small files found.\n")

    print("\n===== Inefficient Files (>= 1 Block) =====")
    if inefficient_files:
        print_inefficient_files(inefficient_files)
    else:
        print("No inefficient files found.\n")

if __name__ == '__main__':
    main()
