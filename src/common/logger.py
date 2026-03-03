# event / message/ fault logger - goes to serial FRAM
import gc
import SPI_Store as fram

# FRAM map configuration
# If no FramMap module is available, fall back to legacy/System11 logger defaults (not universally safe for other targets).
try:
    from FramMap import LOGGER_CONFIG
    AddressStart = LOGGER_CONFIG["AddressStart"]
    LoggerLength = LOGGER_CONFIG["LoggerLength"]
except Exception:
    AddressStart = 0x2400  # legacy/System11 logger region start
    LoggerLength = 0x1FFF  # legacy/System11 logger region length
else:
    # FramMap is present: configuration must be valid or we fail fast
    try:
        AddressStart = LOGGER_CONFIG["AddressStart"]
        LoggerLength = LOGGER_CONFIG["LoggerLength"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("Invalid LOGGER_CONFIG in FramMap: missing or malformed AddressStart/LoggerLength") from exc

AddressEnd = AddressStart + LoggerLength - 16
AddressPointer = AddressStart + LoggerLength - 6
LogEndMarker = "\n"


class Logger:
    def __init__(self):
        address_bytes = fram.read(AddressPointer, 4)
        self.NextWriteAddress = int.from_bytes(address_bytes, "big")
        if self.NextWriteAddress < AddressStart or self.NextWriteAddress >= AddressEnd:
            self.NextWriteAddress = AddressStart

    def delete_log(self):
        self.NextWriteAddress = AddressStart

        clear_data = b"\x00" * 16
        current_address = AddressStart
        while current_address <= AddressEnd:
            fram.write(current_address, clear_data)
            current_address += len(clear_data)

        address_bytes = self.NextWriteAddress.to_bytes(4, "big")
        fram.write(AddressPointer, address_bytes)
        self.log("LOG: Delete All")
        print("address after delete is ", self.NextWriteAddress)

    def log(self, message):
        print(message)
        message += LogEndMarker  # Append the end marker
        for char in message:
            
            # Safety: validate address before every write
            if self.NextWriteAddress < AddressStart or self.NextWriteAddress >= AddressEnd:
                print(f"LOG: Address corruption detected 0x{self.NextWriteAddress:04X}, resetting")
                self.NextWriteAddress = AddressStart
            
            fram.write(self.NextWriteAddress, char.encode("utf-8"))
            self.NextWriteAddress += 1
            if self.NextWriteAddress >= AddressEnd:
                self.NextWriteAddress = AddressStart  # Wrap around if end is reached

        # Save the updated NextWriteAddress back to the fram
        address_bytes = self.NextWriteAddress.to_bytes(4, "big")
        fram.write(AddressPointer, address_bytes)

    def get_logs_stream(self):
        gc.collect()

        if self.NextWriteAddress < AddressStart or self.NextWriteAddress > AddressEnd:
            self.NextWriteAddress = AddressStart
        current_address = self.NextWriteAddress
        read_size = 16
        remaining_bytes = AddressEnd - AddressStart  # whole logger space

        while True:
            bytes_to_read = min(read_size, remaining_bytes)
            data = fram.read(current_address, bytes_to_read)

            for byte in data:
                yield chr(byte).encode("utf-8")
                current_address += 1
                remaining_bytes -= 1
                if current_address >= AddressEnd:
                    current_address = AddressStart
                    break

            if remaining_bytes < 1:
                return


# Singleton instance
logger_instance = Logger()
