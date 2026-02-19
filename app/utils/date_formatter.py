# app/utils/date_formatter.py
from datetime import datetime

# 👇 Change this ONE place if frontend wants a different format
DISPLAY_DATETIME_FORMAT = "%d %B %Y %H:%M"  
# Example: 21 November 2025 08:02

def format_datetime(dt: datetime | None) -> str | None:
    """
    Format a datetime object into a string for the frontend.

    Returns None if dt is None.
    """
    if dt is None:
        return None
    return dt.strftime(DISPLAY_DATETIME_FORMAT)

def formated_datetime(dt: datetime | None) -> str | None:
    """
    Format a datetime object into a string for the frontend.
 
    Returns None if dt is None.
    """
   
    if dt is None:
        return "N/A"
    return dt.strftime(DISPLAY_DATETIME_FORMAT)