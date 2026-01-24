from datetime import datetime, time, timedelta


def calculate_duration(start: time, end: time) -> timedelta:
    """
    Calculate duration between two times.

    Handles midnight crossing (assumes same day or next day).

    Args:
        start: Start time.
        end: End time.

    Returns:
        Duration as timedelta.
    """
    start_dt = datetime.combine(datetime.today(), start)
    end_dt = datetime.combine(datetime.today(), end)

    if end_dt < start_dt:
        # Next day
        end_dt += timedelta(days=1)

    return end_dt - start_dt
