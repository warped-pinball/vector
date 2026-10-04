"""
EM has no machine-side score/game memory to map - scoring lives entirely in
ScoreTrack.py/SharedState. This stub exists only so shared modules that do
`import DataMapper` (Formats.py, backend.py) can load on EM without error.

EM's game config never populates S.gdata["Formats"], so Formats.get_available_
formats()/get_active_format()/set_active_format() already report "no formats"
on their own - they don't call into this module. get_mode_champs() below is
the one DataMapper call in backend.py's shared routes that isn't optional, so
it needs a real (empty) return here rather than crashing /api/mode/champs.
"""


def get_mode_champs():
    return {}
