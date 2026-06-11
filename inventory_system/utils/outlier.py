import math


def detect_outlier(lt_days):
    """Return True if the lead time value is considered an outlier."""
    return lt_days < 0 or lt_days > 30


def trimmed_mean(values, trim=0.05):
    """Remove top/bottom trim fraction, return mean of remaining values."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    cut = max(1, math.floor(n * trim))
    if 2 * cut >= n:
        # Not enough data to trim; return plain mean
        return sum(sorted_vals) / n
    trimmed = sorted_vals[cut:-cut]
    return sum(trimmed) / len(trimmed)


def correct_outlier(lt_days, reference_values):
    """
    If lt_days is an outlier, replace with trimmed mean of reference_values.
    Returns (corrected_value, is_outlier).
    """
    if detect_outlier(lt_days):
        if reference_values:
            corrected = trimmed_mean(reference_values)
        else:
            corrected = 0.0
        return corrected, True
    return lt_days, False
