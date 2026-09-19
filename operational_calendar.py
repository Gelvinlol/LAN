"""Calendar helpers used by duty fairness rules."""

from datetime import date, timedelta


def orthodox_easter(year):
    """Return Orthodox Easter Sunday in the Gregorian calendar."""
    a = year % 4
    b = year % 7
    c = year % 19
    d = (19 * c + 15) % 30
    e = (2 * a + 4 * b - d + 34) % 7
    month = (d + e + 114) // 31
    day = ((d + e + 114) % 31) + 1
    julian_easter = date(year, month, day)
    # Valid for the years supported by the application (Gregorian calendar).
    return julian_easter + timedelta(days=13)


def greek_public_holidays(year):
    easter = orthodox_easter(year)
    return {
        date(year, 1, 1),
        date(year, 1, 6),
        date(year, 3, 25),
        date(year, 5, 1),
        date(year, 8, 15),
        date(year, 10, 28),
        date(year, 12, 25),
        date(year, 12, 26),
        easter - timedelta(days=48),  # Καθαρά Δευτέρα
        easter - timedelta(days=2),   # Μεγάλη Παρασκευή
        easter + timedelta(days=1),   # Δευτέρα του Πάσχα
        easter + timedelta(days=50),  # Αγίου Πνεύματος
    }


def is_weekend_or_holiday(target_date):
    return target_date.weekday() >= 5 or target_date in greek_public_holidays(
        target_date.year
    )
