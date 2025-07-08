
import random
from datetime import datetime, date, timedelta
from app import db
from models import Soldier, DutyType, DutyAssignment, DutySchedule

class SimpleScheduler:
    def __init__(self):
        pass
    
    def generate_daily_schedule(self, schedule_date):
        """Generate a comprehensive duty schedule for a specific date"""
        try:
            # Clear existing assignments for the date
            DutyAssignment.query.filter_by(duty_date=schedule_date).delete()
            
            # Get all active duty types
            duty_types = DutyType.query.filter_by(is_active=True).all()
            
            # Get all available soldiers
            available_soldiers = Soldier.query.filter_by(status='Active', exemption_no_duty=False).all()
            
            if not available_soldiers:
                return False
            
            # Track used soldiers for this day to avoid immediate reuse
            used_soldiers = set()
            assignments_created = 0
            
            # Assign multiple shifts for each duty type
            for duty_type in duty_types:
                # Create 3 shifts per duty type for comprehensive coverage
                for shift_num in [1, 2, 3]:
                    # Get fair candidates for this shift
                    candidates = self._get_fair_candidates(available_soldiers, used_soldiers, schedule_date)
                    
                    # Assign team members for this shift
                    for position in range(duty_type.team_size):
                        if not candidates:
                            # If no unused candidates, allow reuse but prioritize least recent
                            candidates = self._get_fair_candidates(available_soldiers, set(), schedule_date)
                        
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
                    notes=f"Auto-generated schedule with {assignments_created} assignments",
                    is_finalized=False
                )
                db.session.add(schedule_obj)
            else:
                # Update existing schedule but keep finalization status
                schedule_obj.notes = f"Updated auto-generated schedule with {assignments_created} assignments"
            
            db.session.commit()
            return True
            
        except Exception as e:
            print(f"Error generating schedule: {e}")
            db.session.rollback()
            return False
    
    def _get_fair_candidates(self, available_soldiers, used_soldiers, schedule_date):
        """Get soldiers sorted by fairness criteria (same logic as scheduler.py)"""
        candidates = []
        
        for soldier in available_soldiers:
            if soldier.id in used_soldiers:
                continue  # Skip soldiers already assigned today
            
            # Calculate fairness score (lower is better)
            recent_duty_count = self._get_recent_duty_count(soldier, schedule_date)
            days_since_last_duty = self._get_days_since_last_duty(soldier, schedule_date)
            
            # Fairness score: recent duties (weighted more) + days since last duty (inverted)
            fairness_score = (recent_duty_count * 10) - (days_since_last_duty * 0.5)
            
            candidates.append((fairness_score, soldier))
        
        # Sort by fairness score (ascending - lower scores are more fair)
        candidates.sort(key=lambda x: x[0])
        
        # Add some randomization to prevent same ordering every time
        # Shuffle within groups of similar fairness scores
        final_candidates = []
        current_group = []
        current_score = None
        
        for score, soldier in candidates:
            if current_score is None or abs(score - current_score) < 1.0:
                current_group.append(soldier)
                current_score = score
            else:
                # Shuffle current group and add to final list
                random.shuffle(current_group)
                final_candidates.extend(current_group)
                current_group = [soldier]
                current_score = score
        
        # Don't forget the last group
        if current_group:
            random.shuffle(current_group)
            final_candidates.extend(current_group)
        
        return final_candidates
    
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
            return 15  # Safe fallback
