"""
SPI Data (player names, scores, wifi config, tournament scores, some extra config stuff)

"""
import struct

from micropython import const

import SPI_Store as fram
from logger import logger_instance

Log = logger_instance

numberOfPlayers = const(30)
top_mem = const(32767)

memory_map = {
    "MapVersion": {"start": top_mem - 16, "size": 16, "count": 1},
    "names": {"start": top_mem - 16 - (20 * 30), "size": 20, "count": numberOfPlayers},
    "leaders": {"start": top_mem - 16 - (20 * 30) - (35 * 20), "size": 35, "count": 20},
    "tournament": {
        "start": top_mem - 16 - (20 * 30) - (35 * 20) - (12 * 100),
        "size": 12,
        "count": 100,
    },
    "individual": {
        "start": top_mem - 16 - (20 * 30) - (35 * 20) - (12 * 100) - (14 * 20 * 30),
        "size": 14,
        "count": 20,
        "sets": numberOfPlayers,
    },  # count(scores) of 20, and 30 players
    "configuration": {
        "start": top_mem - 16 - (20 * 30) - (35 * 20) - (12 * 100) - (14 * 20 * 30) - (96 * 1),
        "size": 96,
        "count": 1,
    },
    "extras": {
        "start": top_mem - 16 - (20 * 30) - (35 * 20) - (12 * 100) - (14 * 20 * 30) - (96 * 1) - (48 * 1),
        "size": 48,
        "count": 1,
    },
}


def show_mem_map():
    # Calculate the actual start addresses
    memory_map["MapVersion"]["start"] = top_mem - memory_map["MapVersion"]["size"]
    memory_map["names"]["start"] = memory_map["MapVersion"]["start"] - (memory_map["names"]["size"] * memory_map["names"]["count"])
    memory_map["leaders"]["start"] = memory_map["names"]["start"] - (memory_map["leaders"]["size"] * memory_map["leaders"]["count"])
    memory_map["tournament"]["start"] = memory_map["leaders"]["start"] - (memory_map["tournament"]["size"] * memory_map["tournament"]["count"])
    memory_map["individual"]["start"] = memory_map["tournament"]["start"] - (memory_map["individual"]["size"] * memory_map["individual"]["count"] * memory_map["individual"]["sets"])
    memory_map["configuration"]["start"] = memory_map["individual"]["start"] - (memory_map["configuration"]["size"] * memory_map["configuration"]["count"])
    memory_map["extras"]["start"] = memory_map["configuration"]["start"] - (memory_map["extras"]["size"] * memory_map["extras"]["count"])
    # Calculate the end addresses
    for key, value in memory_map.items():
        value["end"] = value["start"] + (value["size"] * value["count"]) - 1
    # Print the final memory map
    for key, value in memory_map.items():
        print(f"{key}: start={value['start']}, end={value['end']}, size={value['size']}, count={value['count']}")


def write_record(structure_name, record, index=0, set=0):
    try:
        # print("write ",structure_name,record,index,set)
        structure = memory_map[structure_name]
        start_address = structure["start"] + index * structure["size"] + structure["size"] * structure["count"] * set
        data = serialize(record, structure_name)
        fram.write(start_address, data)

    except Exception as e:
        error_message = f"Error writing record to {structure_name}: {e}"
        print("Error:", error_message)
        return {"status": "error", "message": error_message}


def serialize(record, structure_name):
    if structure_name == "names":
        return struct.pack("<3s16s", record["initials"].encode(), record["full_name"].encode())
    elif structure_name == "leaders":
        return struct.pack(
            "<3s16s10sI",
            record["initials"].encode(),
            record["full_name"].encode(),
            record["date"].encode(),
            record["score"],
        )
    elif structure_name == "tournament":
        return struct.pack(
            "<3sIBB",
            record["initials"].encode(),
            record["score"],
            record["game"],
            record["index"],
        )
    elif structure_name == "individual":
        return struct.pack("<I10s", record["score"], record["date"].encode())
    elif structure_name == "MapVersion":
        return struct.pack("<16s", record["version"].encode())
    elif structure_name == "configuration":
        return struct.pack(
            "<32s32s16s16s",
            record["ssid"].encode(),
            record["password"].encode(),
            record["gamename"].encode(),
            record["Gpassword"].encode(),
        )
    elif structure_name == "extras":
        return struct.pack(
            "<II20s20s",
            record["enable"],
            record["other"],
            record["lastIP"].encode(),
            record["message"].encode(),
        )
    else:
        raise ValueError("Unknown structure name")


def read_record(structure_name, index=0, set=0):
    structure = memory_map[structure_name]
    if "sets" in structure:
        start_address = structure["start"] + index * structure["size"] + set * structure["size"] * structure["count"]
    else:
        start_address = structure["start"] + index * structure["size"]
    data = fram.read(start_address, structure["size"])
    return deserialize(data, structure_name)


def deserialize(data, structure_name):
    if structure_name == "names":
        try:
            initials, name = struct.unpack("<3s16s", data)
            return {
                "initials": initials.decode().strip("\0"),
                "full_name": name.decode().strip("\0"),
            }
        except Exception:
            return {"intials": " ", "full_name": " "}
    elif structure_name == "leaders":
        try:
            initials, name, date, score = struct.unpack("<3s16s10sI", data)
            return {
                "initials": initials.decode().strip("\0"),
                "full_name": name.decode().strip("\0"),
                "date": date.decode().strip("\0"),
                "score": score,
            }
        except Exception:
            return None
    elif structure_name == "tournament":
        try:
            initials, score, game, index = struct.unpack("<3sIBB", data)
            return {
                "initials": initials.decode().strip("\0"),
                "score": score,
                "game": game,
                "index": index,
            }
        except Exception:
            return None
    elif structure_name == "individual":
        try:
            score, date = struct.unpack("<I10s", data)
            return {"score": score, "date": date.decode().strip("\0")}
        except Exception:
            return {"score": 1, "date": "9"}
    elif structure_name == "MapVersion":
        ver = struct.unpack("<16s", data)
        return {"version": ver[0].decode()}

    elif structure_name == "configuration":
        ssid, password, gamename, gpassword = struct.unpack("<32s32s16s16s", data)
        return {
            "ssid": ssid.decode().strip("\0"),
            "password": password.decode().strip("\0"),
            "gamename": gamename.decode().strip("\0"),
            "Gpassword": gpassword.decode().strip("\0"),
        }

    elif structure_name == "extras":
        # print (data,"length= ",len(data))  #,"s-> ",data.strip('\00'))
        try:
            enable, other, lastIP, message = struct.unpack("<II20s20s", data)
            return {
                "enable": enable,
                "other": other,
                "lastIP": lastIP.decode().strip("\0"),
                "message": message.decode().strip("\0"),
            }
        except Exception:
            print("fault 3452")
            return {"enable": "true", "other": "1", "lastIP": "none", "message": "none"}
    else:
        raise ValueError("Unknown structure name")


def blankStruct(structure_name):
    fake_entry = {
        "initials": "",
        "full_name": "",
        "score": 0,
        "date": "",
        "game": 0,
        "index": 0,
        "enable": 1,
        "lastIP": "none",
        "message": "ok",
        "ssid": "",
        "password": "",
        "Gpassword": " ",
        "gamename": "GenericSystem11",
        "enable": 1,
        "other": 0,
    }
    structure = memory_map[structure_name]
    if "sets" in structure:
        print("   +sets")
        for x in range(structure["sets"]):
            for i in range(structure["count"]):
                write_record(structure_name, fake_entry, i, x)
    else:
        for i in range(structure["count"]):
            write_record(structure_name, fake_entry, i)
    Log.log(f"DATST: blank {structure_name}")


"""
def blankConfig(structure_name):
    if structure_name=="configuration":
        fake_entry = {
            "ssid": "",
            "password": "",
            "Gpassword": " ",
            "gamename": "GenericSystem11_",
            "enable": 1,
            "other": 0
        }
        write_record("configuration", fake_entry, 0, 0)
        Log.log(f"DATST: blank {structure_name}")
"""


def blankIndPlayerScores(playernum):
    fake_entry = {"score": 0, "date": ""}
    structure = memory_map["individual"]
    for i in range(structure["count"]):
        write_record("individual", fake_entry, i, playernum)


def blankAll():
    blankStruct("tournament")
    blankStruct("leaders")
    blankStruct("names")
    blankStruct("individual")
    blankStruct("configuration")
    blankStruct("extras")
    record1 = {"version": "Map Ver: 1.0"}
    write_record("MapVersion", record1, index=0)


def writeIP(ipaddress):
    rec = read_record("extras")
    rec["lastIP"] = ipaddress
    write_record("extras", rec, 0)


if __name__ == "__main__":
    readver = read_record("MapVersion", index=0)
    print("DAT: version= ", readver["version"])

    blankAll()

    record1 = {"version": "Map Ver: 1.0"}
    write_record("MapVersion", record1, index=0)

    print("\n\n")
    show_mem_map()
    print("\n\n")

    readver = read_record("MapVersion", index=0)
    print("read ver string=", readver["version"])
