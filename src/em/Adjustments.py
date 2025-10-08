"""
Added to EM to "disable" the adjustments functionality
"""

# ADJ_FRAM_START = 0x2100  # to 0x2340 +4
# ADJ_FRAM_RECORD_SIZE = 0x80
# ADJ_NUM_SLOTS = 4
# ADJ_NAMES_START = ADJ_FRAM_START + ADJ_FRAM_RECORD_SIZE * ADJ_NUM_SLOTS
# ADJ_NAMES_LENGTH = 16
# ADJ_LAST_LOADED_ADR = 0x2344


def blank_all():
    return


def _get_range_from_gamedef():
    return


def get_names():
    return


def set_name(index, name):
    return


def restore_adjustments(index, reset=True):
    return


def store_adjustments(index):
    return


def get_active_adjustment():
    return


def is_populated(index):
    return


def get_adjustments_status():
    return
