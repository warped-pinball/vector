import gc
import sys

import SPI_Store as fram

# FRAM configuration
AddressStart = 0x2400     #was  4096
AddressEnd = AddressStart + 8192 - 16
AddressPointer = AddressStart + 8192 - 6
NextWriteAddress = 0
LogEndMarker = "\n"  # "<END>"


class Logger:
    def __init__(self):
        global NextWriteAddress
        self._initialize_log()

    def _initialize_log(self):
        global NextWriteAddress
        address_bytes = fram.read(AddressPointer, 4)
        NextWriteAddress = int.from_bytes(address_bytes, "big")
        if NextWriteAddress < AddressStart or NextWriteAddress > AddressEnd:
            NextWriteAddress = AddressStart

    def delete_log(self):
        global NextWriteAddress
        NextWriteAddress = AddressStart

        clear_data = b"\x00" * 16  # 16 bytes
        current_address = AddressStart
        while current_address <= AddressEnd:
            fram.write(current_address, clear_data)
            current_address += len(clear_data)

        address_bytes = NextWriteAddress.to_bytes(4, "big")
        fram.write(AddressPointer, address_bytes)
        self.log("LOG: Delete All")

    def log(self, message):
        global NextWriteAddress
        print(message)
        message += LogEndMarker  # Append the end marker
        for char in message:
            fram.write(
                NextWriteAddress, char.encode("utf-8")
            )  # Write each character as a byte
            NextWriteAddress += 1
            if NextWriteAddress > AddressEnd:
                NextWriteAddress = AddressStart  # Wrap around if end is reached

        # Save the updated NextWriteAddress back to the fram
        address_bytes = NextWriteAddress.to_bytes(4, "big")
        fram.write(AddressPointer, address_bytes)

    def get_logs(self):
        logs = []
        global NextWriteAddress
        current_address = NextWriteAddress
        read_size = 16  # Number of bytes to read at a time

        while True:
            remaining_bytes = AddressEnd - current_address + 1
            bytes_to_read = min(read_size, remaining_bytes)
            data = fram.read(current_address, bytes_to_read)

            for byte in data:
                char = chr(byte)
                logs.append(char)
                current_address += 1
                if current_address > AddressEnd:
                    current_address = AddressStart  # Wrap around if end is reached
                if "".join(logs).endswith(LogEndMarker):
                    return "".join(logs).replace(LogEndMarker, "")

    def get_logs_stream(self):
        gc.collect()
        global NextWriteAddress

        if NextWriteAddress < AddressStart or NextWriteAddress > AddressEnd:
            NextWriteAddress = AddressStart
        current_address = NextWriteAddress
        read_size = 16
        remaining_bytes = AddressEnd - AddressStart

        while True:
            bytes_to_read = min(read_size, remaining_bytes)
            data = fram.read(current_address, bytes_to_read)
            remaining_bytes -= read_size

            for byte in data:
                yield chr(byte).encode("utf-8")
                current_address += 1
                if current_address > AddressEnd:
                    current_address = AddressStart

            if remaining_bytes < 16:
                return


# Singleton instance
logger_instance = Logger()
