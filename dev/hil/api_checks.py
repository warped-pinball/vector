"""Response checks shared by the HIL API harnesses."""

from bench import CheckFailure


def check_switch_diagnostics(payload, require_populated=False):
    """Validate the shape and values returned by the switch diagnostics route."""
    if not isinstance(payload, list):
        raise CheckFailure(f"/api/diagnostics/switches returned {type(payload).__name__}, expected a list")
    if require_populated and not payload:
        raise CheckFailure("/api/diagnostics/switches returned no switch records for a configured switch table")

    for index, switch in enumerate(payload):
        if not isinstance(switch, dict):
            raise CheckFailure(f"/api/diagnostics/switches item {index} is not an object")
        if not {"row", "col", "val", "label"}.issubset(switch):
            raise CheckFailure(f"/api/diagnostics/switches item {index} is missing required fields")
        if type(switch["row"]) is not int or not 1 <= switch["row"] <= 8:
            raise CheckFailure(f"/api/diagnostics/switches item {index} has an invalid row")
        if type(switch["col"]) is not int or not 1 <= switch["col"] <= 8:
            raise CheckFailure(f"/api/diagnostics/switches item {index} has an invalid column")
        if type(switch["val"]) is not int or not 0 <= switch["val"] <= 100:
            raise CheckFailure(f"/api/diagnostics/switches item {index} has an invalid value")
        if not isinstance(switch["label"], str) or not switch["label"]:
            raise CheckFailure(f"/api/diagnostics/switches item {index} has an invalid label")

    return payload
