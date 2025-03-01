import gc
import uctypes

def inspect_stack():
    # Get the current stack pointer
    stack_pointer = gc.mem_info()[1]
    print(f"Stack pointer: {stack_pointer}")

    # Print the stack data
    stack_data = uctypes.bytearray_at(stack_pointer, 64)  # Adjust the size as needed
    print("Stack data:", stack_data)

    # Check the data types of the stack elements
    for i in range(0, len(stack_data), 4):
        element = stack_data[i:i+4]
        try:
            value = int.from_bytes(element, 'little')
            print(f"Element {i//4}: {value} (int)")
        except ValueError:
            print(f"Element {i//4}: {element} (bytes)")

    # Inspect memory addresses
    for i in range(0, len(stack_data), 4):
        address = int.from_bytes(stack_data[i:i+4], 'little')
        try:
            memory_data = uctypes.bytearray_at(address, 16)  # Adjust the size as needed
            print(f"Memory at {address}: {memory_data}")
        except ValueError:
            print(f"Invalid address: {address}")

# Call the function to inspect the stack
inspect_stack()
