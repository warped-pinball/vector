# Hardware Faults
HDWR00 = "HDWR00: Unknown Hardware Error"
HDWR01 = "HDWR01: Bus Activity"

ALL_HDWR = [HDWR00, HDWR01]

# Software Faults
SFWR00 = "SFWR00: Unknown Software Error"
SFTW01 = "SFTW01: Drop Through"

ALL_SFWR = [SFWR00, SFTW01]

# Configuration Faults
CONF00 = "CONF00: Unknown Configuration Error"
CONF01 = "CONF01: Invalid Configuration"

ALL_CONF = [CONF00, CONF01]

#WiFi Faults
WIFI00 = "WIFI00: Unknown Wifi Error"
WIFI01 = "WIFI01: Invalid Wifi Credentaials"
WIFI02 = "WIFI02: No Wifi Signal"

ALL_WIFI = [WIFI00, WIFI01, WIFI02]

DUNO00 = "DUNO00: Unknown Error"

ALL = ALL_HDWR + ALL_SFWR + ALL_CONF + ALL_WIFI + [DUNO00]

def raise_fault(fault, msg=None):
    import SharedState as S
    if not isinstance(msg, str):
        msg = str(msg)

    full_fault = f"{fault} - {msg}" if msg else fault
    S.faults.append(full_fault)
    
    from logger import logger_instance as Log
    Log.log(f"Fault raised: {full_fault}")

def fault_is_raised(fault):
    import SharedState as S
    if isinstance(fault, str):
        faults = [fault]
    elif isinstance(fault, list):
        faults = fault
    else:
        raise ValueError("fault must be a string or a list of strings")
    
    for f in faults:
        fault_code = f.split(":")[0]
        if fault_code in [x.split(":")[0] for x in S.faults]:
            return True
    return False