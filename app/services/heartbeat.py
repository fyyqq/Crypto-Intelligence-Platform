"""In-process heartbeats: a background loop calls beat("name") after each good
pass and /site_health reads how long ago that was. Process memory only (the
loops and the bot run in the same Reflex process)."""
import time

_beats: dict[str, float] = {}


def beat(name: str) -> None:
    _beats[name] = time.time()


def age(name: str) -> float | None:
    """Seconds since the last beat, or None if it never beat in this process."""
    at = _beats.get(name)
    return None if at is None else time.time() - at
