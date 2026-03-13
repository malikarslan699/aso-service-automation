"""Dynamic scheduler - placeholder for Phase 2 implementation.

Generates random scheduling windows:
- Random time between 9 AM - 10 PM
- Never same hour 2 days in a row
- 2 random skip days per week
"""
import random
from datetime import datetime, time


def generate_daily_schedule(last_hour: int = -1) -> dict:
    """Generate a random execution time for today.

    Args:
        last_hour: The hour used yesterday (-1 if none)

    Returns:
        dict with hour, minute, should_skip
    """
    # 2 skip days per week = ~28.5% chance per day
    if random.random() < 0.285:
        return {"should_skip": True, "hour": 0, "minute": 0}

    # Pick random hour 9-22, avoiding yesterday's hour
    available_hours = [h for h in range(9, 22) if h != last_hour]
    hour = random.choice(available_hours)
    minute = random.randint(0, 59)

    return {"should_skip": False, "hour": hour, "minute": minute}
