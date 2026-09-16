
import random
import logging
from datetime import timedelta

from app import db
from models import Soldier, DutyType, DutyAssignment, DutySchedule, SoldierLeave


logger = logging.getLogger(__name__)

class SimpleScheduler:
    def __init__(self):
        self._fairness_reference_date = None
        self._fairness_metrics = {}
        self._duty_type_counts = {}
        self._last_duty_type = {}
    
    def generate_daily_schedule(self, schedule_date):
        """Generate a comprehensive duty schedule for a specific date"""
        try:
            # Clear existing assignments for the date
            DutyAssignment.query.filter_by(duty_date=schedule_date).delete()
            
            # Get all active duty types
            duty_types = DutyType.query.filter_by(is_active=True).all()
            
            # Get all available soldiers
            soldiers_on_leave = db.session.query(SoldierLeave.soldier_id).filter(
                SoldierLeave.status == 'Approved',
                SoldierLeave.start_date <= schedule_date,
                SoldierLeave.end_date >= schedule_date,
            )
            available_soldiers = Soldier.query.filter(
                Soldier.status == 'Active',
                Soldier.exemption_no_duty.is_(False),
                ~Soldier.id.in_(soldiers_on_leave),
            ).all()
            available_soldiers = [
                soldier for soldier in available_soldiers if soldier.is_available_for_duty()
            ]
            
            if not available_soldiers:
                return False

            self._prepare_fairness_metrics(available_soldiers, schedule_date)
            
            # Track used soldiers for this day to avoid immediate reuse
            used_soldiers = set()
            assignments_created = 0
            assignments_required = sum(
                duty_type.team_size * max(1, duty_type.shifts_per_day)
                for duty_type in duty_types
            )
            
            # Assign multiple shifts for each duty type
            for duty_type in duty_types:
                # Respect the configured number of shifts for each duty type.
                for shift_num in range(1, max(1, duty_type.shifts_per_day) + 1):
                    # Get fair candidates for this shift
                    candidates = self._get_fair_candidates(
                        available_soldiers, used_soldiers, schedule_date, duty_type.id
                    )
                    
                    # Assign team members for this shift
                    for position in range(duty_type.team_size):
                        if not candidates:
                            # Never give a soldier a second duty on the same day.
                            # An unfilled slot is safer than a duplicate assignment.
                            break
                        
                        if candidates:
                            soldier = candidates.pop(0)  # Take the most fair candidate
                            
                            assignment = DutyAssignment(
                                soldier_id=soldier.id,
                                duty_type_id=duty_type.id,
                                duty_date=schedule_date,
                                shift_number=shift_num,
                                position_in_team=position + 1,
                                notes=f"Auto-assigned by scheduler"
                            )
                            
                            db.session.add(assignment)
                            assignments_created += 1
                            used_soldiers.add(soldier.id)
            
            # Create schedule record
            schedule_obj = DutySchedule.query.filter_by(schedule_date=schedule_date).first()
            if not schedule_obj:
                schedule_obj = DutySchedule(
                    schedule_date=schedule_date,
                    notes=(
                        f"Auto-generated schedule with {assignments_created}/"
                        f"{assignments_required} assignments"
                    ),
                    is_finalized=False
                )
                db.session.add(schedule_obj)
            else:
                # Update existing schedule but keep finalization status
                schedule_obj.notes = (
                    f"Updated auto-generated schedule with {assignments_created}/"
                    f"{assignments_required} assignments"
                )
            
            db.session.commit()
            return assignments_created == assignments_required
            
        except Exception as e:
            logger.exception("Error generating schedule for %s", schedule_date)
            db.session.rollback()
            return False
    
    def _get_fair_candidates(
        self, available_soldiers, used_soldiers, schedule_date, duty_type_id=None
    ):
        """Rank candidates by total fairness and rotation between duty types."""
        soldier_ids = {soldier.id for soldier in available_soldiers}
        if (
            self._fairness_reference_date != schedule_date
            or not soldier_ids.issubset(self._fairness_metrics)
        ):
            self._prepare_fairness_metrics(available_soldiers, schedule_date)

        candidates = []
        
        for soldier in available_soldiers:
            if soldier.id in used_soldiers:
                continue  # Skip soldiers already assigned today
            
            total_count, recent_count, last_duty_date = self._fairness_metrics.get(
                soldier.id, (0, 0, None)
            )

            # Never-assigned soldiers are a strict priority tier. Previously they
            # were treated as "30 days since last duty", so somebody whose last
            # duty was more than 30 days ago could incorrectly outrank them.
            if last_duty_date is None:
                fairness_key = (0, 0, 0, 0, 0)
            else:
                days_since_last_duty = (schedule_date - last_duty_date).days
                historical_score = (recent_count * 10) - (days_since_last_duty * 0.5)
                repeats_last_type = int(
                    duty_type_id is not None
                    and self._last_duty_type.get(soldier.id) == duty_type_id
                )
                same_type_count = self._duty_type_counts.get(
                    (soldier.id, duty_type_id), 0
                ) if duty_type_id is not None else 0
                fairness_key = (
                    1,
                    repeats_last_type,
                    same_type_count,
                    total_count,
                    historical_score,
                )

            candidates.append((fairness_key, soldier))

        # Shuffle first so genuinely equal candidates rotate, then use a stable
        # sort to preserve the strict fairness tiers above.
        random.shuffle(candidates)
        candidates.sort(key=lambda item: item[0])
        return [soldier for _, soldier in candidates]

    def _prepare_fairness_metrics(self, soldiers, reference_date, days_back=7):
        """Load all finalized-duty metrics in one query for consistent ranking."""
        soldier_ids = [soldier.id for soldier in soldiers]
        self._fairness_reference_date = reference_date
        self._fairness_metrics = {
            soldier_id: (0, 0, None) for soldier_id in soldier_ids
        }
        self._duty_type_counts = {}
        self._last_duty_type = {}
        if not soldier_ids:
            return

        cutoff_date = reference_date - timedelta(days=days_back)
        rows = db.session.query(
            DutyAssignment.soldier_id,
            DutyAssignment.duty_type_id,
            DutyAssignment.duty_date,
        ).join(
            DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
        ).filter(
            DutyAssignment.soldier_id.in_(soldier_ids),
            DutyAssignment.duty_date < reference_date,
            DutySchedule.is_finalized.is_(True),
        ).order_by(
            DutyAssignment.duty_date.desc(), DutyAssignment.id.desc()
        ).all()

        for soldier_id, duty_type_id, duty_date in rows:
            total_count, recent_count, last_duty_date = self._fairness_metrics[soldier_id]
            self._fairness_metrics[soldier_id] = (
                total_count + 1,
                recent_count + int(duty_date >= cutoff_date),
                last_duty_date or duty_date,
            )
            type_key = (soldier_id, duty_type_id)
            self._duty_type_counts[type_key] = self._duty_type_counts.get(type_key, 0) + 1
            if soldier_id not in self._last_duty_type:
                self._last_duty_type[soldier_id] = duty_type_id
    
    def _get_recent_duty_count(self, soldier, reference_date, days_back=7):
        """Get number of duties in the last N days (only finalized schedules)"""
        try:
            cutoff_date = reference_date - timedelta(days=days_back)
            
            count = db.session.query(DutyAssignment).join(
                DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
            ).filter(
                DutyAssignment.soldier_id == soldier.id,
                DutyAssignment.duty_date >= cutoff_date,
                DutyAssignment.duty_date < reference_date,
                DutySchedule.is_finalized == True
            ).count()
            
            return count
        except Exception as e:
            logger.exception("Could not count recent duties for soldier %s", soldier.id)
            return 0  # Safe fallback
    
    def _get_days_since_last_duty(self, soldier, reference_date):
        """Get number of days since soldier's last duty (only finalized schedules)"""
        try:
            last_assignment = db.session.query(DutyAssignment).join(
                DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
            ).filter(
                DutyAssignment.soldier_id == soldier.id,
                DutyAssignment.duty_date < reference_date,
                DutySchedule.is_finalized == True
            ).order_by(DutyAssignment.duty_date.desc()).first()
            
            if not last_assignment:
                return 30  # If no previous duty, treat as 30 days (high priority)
            
            days_diff = (reference_date - last_assignment.duty_date).days
            return days_diff
        except Exception as e:
            logger.exception("Could not find last duty for soldier %s", soldier.id)
            return 15  # Safe fallback
