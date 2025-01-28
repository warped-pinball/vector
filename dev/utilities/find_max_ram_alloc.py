import gc


def find_max_alloc():
    gc.collect()  # Clean up memory
    max_size = 0
    step = 1024  # Start with 1 KB steps
    while True:
        try:
            test_block = bytearray(max_size + step)
            max_size += step
        except MemoryError:
            break
    return max_size


max_block = find_max_alloc()
print(f"Maximum allocatable block: {max_block} bytes")
