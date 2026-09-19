"""Finalized-duty reporting and fairness metrics."""

from collections import Counter, defaultdict
from datetime import datetime, time, timedelta

from models import DutyAssignment, DutySchedule
from operational_calendar import is_weekend_or_holiday


def _assignment_bounds(assignment):
    occurrences = assignment.get_shift_occurrences()
    if not occurrences:
        fallback = datetime.combine(assignment.duty_date, time.min)
        return fallback, fallback
    return min(start for start, _end in occurrences), max(
        end for _start, end in occurrences
    )


def _is_night_assignment(assignment):
    """Night means any assigned period overlapping 22:00–06:00."""
    for start_at, end_at in assignment.get_shift_occurrences():
        day = start_at.date() - timedelta(days=1)
        while day <= end_at.date():
            night_start = datetime.combine(day, time(22, 0))
            night_end = datetime.combine(day + timedelta(days=1), time(6, 0))
            if start_at < night_end and end_at > night_start:
                return True
            day += timedelta(days=1)
    return False


def build_fairness_report(start_date, end_date):
    assignments = DutyAssignment.query.join(
        DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
    ).filter(
        DutySchedule.is_finalized.is_(True),
        DutyAssignment.duty_date >= start_date,
        DutyAssignment.duty_date <= end_date,
    ).order_by(
        DutyAssignment.soldier_id, DutyAssignment.duty_date, DutyAssignment.id
    ).all()

    grouped = defaultdict(list)
    duty_type_totals = Counter()
    for assignment in assignments:
        grouped[assignment.soldier_id].append(assignment)
        duty_type_totals[assignment.duty_type.name] += 1

    rows = []
    for soldier_assignments in grouped.values():
        soldier = soldier_assignments[0].soldier
        night_count = sum(_is_night_assignment(item) for item in soldier_assignments)
        special_count = sum(
            is_weekend_or_holiday(item.duty_date) for item in soldier_assignments
        )
        duty_counts = Counter(item.duty_type.name for item in soldier_assignments)

        bounded = sorted(
            ((_assignment_bounds(item), item) for item in soldier_assignments),
            key=lambda entry: entry[0][0],
        )
        rest_hours = []
        for previous, current in zip(bounded, bounded[1:]):
            previous_end = previous[0][1]
            current_start = current[0][0]
            rest_hours.append(max(0, (current_start - previous_end).total_seconds() / 3600))

        total = len(soldier_assignments)
        score = total + (night_count * 0.5) + (special_count * 0.5)
        rows.append({
            'soldier': soldier,
            'total': total,
            'night': night_count,
            'special': special_count,
            'average_rest_hours': (
                round(sum(rest_hours) / len(rest_hours), 1) if rest_hours else None
            ),
            'rest_samples': rest_hours,
            'duty_counts': duty_counts,
            'top_duty': duty_counts.most_common(1)[0] if duty_counts else None,
            'score': score,
        })

    average_score = (
        sum(row['score'] for row in rows) / len(rows) if rows else 0
    )
    for row in rows:
        if average_score and row['score'] >= max(average_score * 1.2, average_score + 1):
            row['burden'] = 'high'
        elif average_score and row['score'] <= average_score * 0.8:
            row['burden'] = 'low'
        else:
            row['burden'] = 'balanced'

    rows.sort(key=lambda row: (-row['score'], row['soldier'].name))
    total_night = sum(row['night'] for row in rows)
    total_special = sum(row['special'] for row in rows)
    report_rest = [hours for row in rows for hours in row['rest_samples']]
    return {
        'rows': rows,
        'total_assignments': len(assignments),
        'total_soldiers': len(rows),
        'total_night': total_night,
        'total_special': total_special,
        'average_assignments': round(len(assignments) / len(rows), 1) if rows else 0,
        'average_rest_hours': (
            round(sum(report_rest) / len(report_rest), 1) if report_rest else None
        ),
        'duty_type_totals': duty_type_totals.most_common(),
        'average_score': round(average_score, 1),
    }
