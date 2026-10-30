# WPC

# This file is part of the Warped Pinball WOC - Wifi Project.
# https://creativecommons.org/licenses/by-nc/4.0/
# This work is licensed under CC BY-NC 4.0
"""Routes only WPC boards define, imported by backend.py when present."""

from backend import add_route


@add_route("/api/time/trigger_midnight_madness", auth=True)
def app_triggerMidnightMadness(request):
    """
    @api
    summary: Immediately trigger Midnight Madness (WPC only)
    auth: true
    response:
      status_codes:
        - code: 200
          description: Event triggered
      body:
        example: "ok"
    @end
    """
    import Time

    Time.trigger_midnight_madness()
