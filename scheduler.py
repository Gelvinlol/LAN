import random
from datetime import datetime, date, timedelta
from app import db
from models import Soldier, DutyType, DutyAssignment, DutyTimeSlot, DutySchedule
import logging

class DutyScheduler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
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
                self.logger.warning("No available soldiers for duty assignment")
                return False
            
            if len(available_soldiers) < 10:
                self.logger.warning(f"Limited soldiers available: {len(available_soldiers)}")
            
            # Track assignments for fairness - but allow reuse for comprehensive coverage
            used_soldiers = set()
            all_assignments_successful = True
            
            # First pass - assign primary duties with no reuse
            for duty_type in duty_types:
                success = self._assign_duty_type(duty_type, schedule_date, available_soldiers, used_soldiers)
                if not success:
                    all_assignments_successful = False
            
            # Second pass - fill additional shifts with soldier reuse allowed
            self._assign_additional_coverage(duty_types, schedule_date, available_soldiers)
            
            # Create or update schedule record
            schedule_obj = DutySchedule.query.filter_by(schedule_date=schedule_date).first()
            if not schedule_obj:
                schedule_obj = DutySchedule(
                    schedule_date=schedule_date,
                    notes=f"Auto-generated comprehensive schedule"
                )
                db.session.add(schedule_obj)
            
            schedule_obj.is_finalized = True
            
            db.session.commit()
            return True
            
        except Exception as e:
            self.logger.error(f"Error generating schedule: {e}")
            db.session.rollback()
            return False
    
    def _assign_additional_coverage(self, duty_types, schedule_date, available_soldiers):
        """Assign additional shifts to provide better coverage, allowing soldier reuse"""
        try:
            # Create additional shifts for key duties
            key_duties = ['Περίπολος', 'Κεντρική Πύλη', 'Θαλαμοφύλακας']
            
            for duty_type in duty_types:
                if duty_type.name in key_duties:
                    # Add evening and night shifts
                    evening_shifts = [2, 3]  # Evening and night shifts
                    
                    for shift_num in evening_shifts:
                        # Select soldiers who haven't been assigned to this specific duty today
                        assigned_to_this_duty = set()
                        existing_assignments = DutyAssignment.query.filter_by(
                            duty_date=schedule_date,
                            duty_type_id=duty_type.id
                        ).all()
                        
                        for assignment in existing_assignments:
                            assigned_to_this_duty.add(assignment.soldier_id)
                        
                        # Get soldiers not assigned to this duty type today
                        available_for_duty = [s for s in available_soldiers 
                                            if s.id not in assigned_to_this_duty]
                        
                        if len(available_for_duty) >= duty_type.team_size:
                            # Sort by recent duty count
                            candidates = self._get_fair_candidates(available_for_duty, set(), schedule_date)
                            
                            # Assign team
                            for i in range(min(duty_type.team_size, len(candidates))):
                                assignment = DutyAssignment(
                                    soldier_id=candidates[i].id,
                                    duty_type_id=duty_type.id,
                                    duty_date=schedule_date,
                                    shift_number=shift_num,
                                    position_in_team=i + 1,
                                    notes=f"Additional coverage shift {shift_num}"
                                )
                                db.session.add(assignment)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error assigning additional coverage: {e}")
            return False
    
    def _assign_duty_type(self, duty_type, schedule_date, available_soldiers, used_soldiers):
        """Assign soldiers to a specific duty type for all its shifts"""
        try:
            # Get time slots for this duty type
            time_slots = DutyTimeSlot.query.filter_by(duty_type_id=duty_type.id).all()
            
            if not time_slots:
                # Create default time slot if none exists
                default_slot = DutyTimeSlot(
                    duty_type_id=duty_type.id,
                    shift_number=1,
                    start_time="08:00",
                    end_time="18:00"
                )
                db.session.add(default_slot)
                db.session.commit()
                time_slots = [default_slot]
            
            # Group time slots by shift number
            shifts = {}
            for slot in time_slots:
                if slot.shift_number not in shifts:
                    shifts[slot.shift_number] = []
                shifts[slot.shift_number].append(slot)
            
            # Assign soldiers to each shift
            for shift_number in shifts.keys():
                success = self._assign_shift(duty_type, shift_number, schedule_date, 
                                           available_soldiers, used_soldiers)
                if not success:
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error assigning duty type {duty_type.name}: {e}")
            return False
    
    def _assign_shift(self, duty_type, shift_number, schedule_date, available_soldiers, used_soldiers):
        """Assign soldiers to a specific shift of a duty type"""
        try:
            soldiers_needed = duty_type.team_size
            
            # Get soldiers sorted by fairness (least recent duties first)
            candidate_soldiers = self._get_fair_candidates(available_soldiers, used_soldiers, schedule_date)
            
            if len(candidate_soldiers) < soldiers_needed:
                self.logger.warning(f"Not enough available soldiers for {duty_type.name} shift {shift_number}")
                # Assign as many as possible
                soldiers_needed = len(candidate_soldiers)
                if soldiers_needed == 0:
                    return False
            
            # Select soldiers for this shift
            selected_soldiers = candidate_soldiers[:soldiers_needed]
            
            # Create assignments
            for position, soldier in enumerate(selected_soldiers, 1):
                assignment = DutyAssignment(
                    soldier_id=soldier.id,
                    duty_type_id=duty_type.id,
                    duty_date=schedule_date,
                    shift_number=shift_number,
                    position_in_team=position,
                    notes=f"Auto-assigned by scheduler"
                )
                db.session.add(assignment)
                used_soldiers.add(soldier.id)
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error assigning shift {shift_number} for {duty_type.name}: {e}")
            return False
    
    def _get_fair_candidates(self, available_soldiers, used_soldiers, schedule_date):
        """Get soldiers sorted by fairness criteria"""
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
        """Get number of duties in the last N days"""
        try:
            cutoff_date = reference_date - timedelta(days=days_back)
            
            count = db.session.query(DutyAssignment).filter(
                DutyAssignment.soldier_id == soldier.id,
                DutyAssignment.duty_date >= cutoff_date,
                DutyAssignment.duty_date < reference_date
            ).count()
            
            return count
        except Exception as e:
            self.logger.error(f"Error getting recent duty count: {e}")
            return 0  # Safe fallback
    
    def _get_days_since_last_duty(self, soldier, reference_date):
        """Get number of days since soldier's last duty"""
        try:
            last_assignment = db.session.query(DutyAssignment).filter(
                DutyAssignment.soldier_id == soldier.id,
                DutyAssignment.duty_date < reference_date
            ).order_by(DutyAssignment.duty_date.desc()).first()
            
            if not last_assignment:
                return 30  # If no previous duty, treat as 30 days (high priority)
            
            days_diff = (reference_date - last_assignment.duty_date).days
            return days_diff
        except Exception as e:
            self.logger.error(f"Error getting days since last duty: {e}")
            return 15  # Safe fallback
