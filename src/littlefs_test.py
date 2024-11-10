import os

# Define a mount point (e.g., "/flash")
MOUNT_POINT = "/flash"

# Initialize the LittleFS
try:
    os.mount(MOUNT_POINT, "littlefs")
except OSError:
    # If mount fails, format the partition with LittleFS
    os.VfsLfs2.mkfs(MOUNT_POINT)
    os.mount(MOUNT_POINT, "littlefs")

# Writing a File
def write_file(filename, data):
    with open(f"{MOUNT_POINT}/{filename}", "wb") as file:
        file.write(data)

# Reading a File
def read_file(filename):
    with open(f"{MOUNT_POINT}/{filename}", "rb") as file:
        return file.read()

# Example Usage
filename = "largefile.bin"
data = bytearray([0x01] * 1024)  # Example large data (1KB of 0x01 bytes)

# Write data to file
write_file(filename, data)

# Read data from file
read_data = read_file(filename)
print(f"Read {len(read_data)} bytes from {filename}")
