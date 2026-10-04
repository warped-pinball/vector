"""
Added to EM to "disable" the Midnight Madness clock functionality.

EM reports Clock != "MM" (see GameInfo in GameDefsLoad.py/SPI_DataStore.py),
so /api/time/midnight_madness_available correctly tells the UI this feature
doesn't exist here. This stub only exists so that the unguarded
/api/time/trigger_midnight_madness route (backend.py) can still `import Time`
without error if it's ever hit directly.
"""


def trigger_midnight_madness():
    return
