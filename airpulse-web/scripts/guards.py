"""Checks a forecast must pass before it leaves the engine for the customer application. Used by export_data.py.

    python scripts/guards.py 0.2 0.3 0.5 UP      # exit code 0 if the forecast is valid, 1 with a message otherwise"""
import math, sys

CLASSES = ("DOWN", "FLAT", "UP")


def valid_forecast(d, f, u, predicted, where=""):
    """A forecast is exported only if it is a probability distribution over the three directions and names one of them.
    A month for which no forecast was issued (all four values missing) passes untouched."""
    if d is None and f is None and u is None and predicted is None: return
    ok = (all(isinstance(x, float) and math.isfinite(x) and 0.0 <= x <= 1.0 for x in (d, f, u)) and abs(d + f + u - 1.0) < 1e-6 and predicted in CLASSES)
    if not ok: sys.exit(f"invalid forecast refused ({where}): probabilities {d}, {f}, {u}; direction {predicted!r}")


if __name__ == "__main__":
    a = sys.argv[1:]
    valid_forecast(float(a[0]), float(a[1]), float(a[2]), a[3], "command line")
