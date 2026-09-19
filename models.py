from datetime import datetime, date
from app import db
from flask_login import UserMixin
from werkzeug.security import check_password_hash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(50), nullable=False)  # Διοικητής, Υπασπιστήριο, ΑΥΔΜ, ΓΡΑΦΙΟ ΑΡΧΗΛΟΧΕΙΑ
    full_name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)
    permissions = db.relationship(
        'UserPermission', backref='user', lazy=True,
        cascade='all, delete-orphan', order_by='UserPermission.permission_key'
    )

    @property
    def is_active(self):
        return bool(self.active)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_commander(self):
        return self.role == "Διοικητής"
    
    def can_view_logs(self):
        return self.has_permission('logs.view')

    def has_permission(self, permission_key):
        if self.is_commander():
            return True
        assigned = {permission.permission_key for permission in self.permissions}
        if permission_key in assigned:
            return True
        if permission_key.endswith('.view'):
            return f"{permission_key[:-5]}.manage" in assigned
        return False
    
    def __repr__(self):
        return f'<User {self.username}>'


class UserPermission(db.Model):
    __table_args__ = (
        db.UniqueConstraint('user_id', 'permission_key', name='uq_user_permission'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey('user.id'), nullable=False, index=True
    )
    permission_key = db.Column(db.String(80), nullable=False)

    def __repr__(self):
        return f'<UserPermission {self.user_id}:{self.permission_key}>'


class UnitSettings(db.Model):
    """Singleton record containing the unit's administrative identity."""

    id = db.Column(db.Integer, primary_key=True, default=1)
    camp_name = db.Column(db.String(150), nullable=False)
    unit_name = db.Column(db.String(150), nullable=False)
    battalion_name = db.Column(db.String(150), nullable=False)
    branch = db.Column(db.String(100), nullable=False)
    formation_name = db.Column(db.String(150))
    unit_code = db.Column(db.String(50))
    location = db.Column(db.String(200))
    commander_rank = db.Column(db.String(80))
    commander_name = db.Column(db.String(120))
    contact_phone = db.Column(db.String(30))
    contact_email = db.Column(db.String(120))
    motto = db.Column(db.String(200))
    notes = db.Column(db.Text)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    updated_at = db.Column(
        db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    updater = db.relationship('User', backref='unit_settings_updates')

    def __repr__(self):
        return f'<UnitSettings {self.unit_name}>'

class ActivityLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    target_type = db.Column(db.String(50))  # soldier, duty, schedule, etc.
    target_id = db.Column(db.Integer)
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', backref=db.backref('activity_logs', lazy=True))
    
    def __repr__(self):
        return f'<ActivityLog {self.action} by {self.user.username}>'

class Soldier(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    military_id = db.Column(db.String(20), unique=True, nullable=False)
    enlistment_date = db.Column(db.Date, nullable=False)
    specialty = db.Column(db.String(100))
    status = db.Column(db.String(50), default='Active')  # Active, On Leave
    exemption_no_duty = db.Column(db.Boolean, default=False)  # Άνευ υπηρεσίας
    exemption_no_shaving = db.Column(db.Boolean, default=False)  # Άνευ ξυρίσματος
    exemption_no_boots = db.Column(db.Boolean, default=False)  # Άνευ αρβυλών
    days_out_of_service = db.Column(db.Integer, default=0)  # Μέρες ΕΥ (Εκτός Υπηρεσίας)
    out_of_service_reason = db.Column(db.String(200))  # Λόγος ΕΥ
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Συνέντευξη Υπασπιστηρίου Fields
    birth_date = db.Column(db.Date)  # ΗΜΕΡΟΜΗΝΙΑ ΓΕΝΝΗΣΗΣ
    mother_name = db.Column(db.String(100))  # ΟΝΟΜΑ ΜΗΤΡΟΣ
    father_name = db.Column(db.String(100))  # ΟΝΟΜΑ ΠΑΤΡΟΣ
    profession = db.Column(db.String(100))  # ΕΠΑΓΓΕΛΜΑ
    mother_profession = db.Column(db.String(100))  # ΕΠΑΓΓΕΛΜΑ ΜΗΤΡΟΣ
    father_profession = db.Column(db.String(100))  # ΕΠΑΓΓΕΛΜΑ ΠΑΤΡΟΣ
    brothers_count = db.Column(db.Integer, default=0)  # ΑΡΙΘΜΟΣ ΑΔΕΛΦΩΝ
    sisters_count = db.Column(db.Integer, default=0)  # ΑΡΙΘΜΟΣ ΑΔΕΛΦΩΝ
    residence_address = db.Column(db.String(200))  # ΔΙΕΥΘΥΝΣΗ ΔΙΑΜΟΝΗΣ
    residence_city = db.Column(db.String(100))  # ΠΟΛΗ ΔΙΑΜΟΝΗΣ
    residence_prefecture = db.Column(db.String(100))  # ΝΟΜΟΣ ΔΙΑΜΟΝΗΣ
    personal_phone = db.Column(db.String(20))  # ΤΗΛΕΦΩΝΟ ΠΡΟΣΩΠΙΚΟ
    parents_phone = db.Column(db.String(20))  # ΤΗΛΕΦΩΝΟ ΓΟΝΕΩΝ
    education = db.Column(db.String(200))  # ΣΠΟΥΔΕΣ
    special_skills = db.Column(db.String(300))  # ΕΙΔΙΚΕΣ ΓΝΩΣΕΙΣ
    category = db.Column(db.String(50))  # ΚΑΤΗΓΟΡΙΑ (ΕΚΠΑΙΔΕΥΟΜΕΝΟΣ, ΟΡΓΑΝΙΚΟΣ, ΦΡΟΥΡΑ)
    medical_category = db.Column(db.String(20))  # ΙΑΤΡΙΚΗ ΚΑΤΗΓΟΡΙΑ (Ι1, Ι2, Ι3 ΕΝΟΠΛΟ, Ι3 ΑΟΠΛΟ, Ι4)
    amka = db.Column(db.String(11))  # ΑΜΚΑ
    tax_number = db.Column(db.String(20))  # ΑΡΙΘ. ΦΟΡΟΛΟΓ ΜΗΤΡΩΟΥ
    iban = db.Column(db.String(27))  # ΙΒΑΝ
    bank = db.Column(db.String(50))  # ΤΡΑΠΕΖΑ
    email = db.Column(db.String(120))  # EMAIL
    parent_email = db.Column(db.String(120))  # EMAIL ΓΟΝΕΑ
    interview_notes = db.Column(db.Text)  # ΠΑΡΑΤΗΡΗΣΕΙΣ
    
    # Relationships
    duty_assignments = db.relationship('DutyAssignment', backref='soldier', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Soldier {self.name}>'
    
    def is_available_for_duty(self):
        """Check if soldier is available for duty assignment"""
        if self.status != 'Active' or self.exemption_no_duty:
            return False
        
        # Ι4 cannot do any duties
        if self.medical_category == 'Ι4':
            return False
            
        return True
    
    def is_available_for_armed_duty(self):
        """Check if soldier can do armed duties"""
        if not self.is_available_for_duty():
            return False
            
        # Only Ι1, Ι2, Ι3 ΕΝΟΠΛΟ can do armed duties
        return self.medical_category in ['Ι1', 'Ι2', 'Ι3 ΕΝΟΠΛΟ']
    
    def is_available_for_unarmed_duty(self):
        """Check if soldier can do unarmed duties (like kitchen, guard room)"""
        if not self.is_available_for_duty():
            return False
            
        # Ι1, Ι2, Ι3 ΕΝΟΠΛΟ, Ι3 ΑΟΠΛΟ can do unarmed duties
        return self.medical_category in ['Ι1', 'Ι2', 'Ι3 ΕΝΟΠΛΟ', 'Ι3 ΑΟΠΛΟ']
    
    def get_duty_count_last_days(self, days=7):
        """Get finalized duties in the last N days; drafts never count."""
        from datetime import datetime, timedelta
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        return db.session.query(DutyAssignment).join(
            DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
        ).filter(
            DutyAssignment.soldier_id == self.id,
            DutyAssignment.duty_date >= cutoff_date.date(),
            DutySchedule.is_finalized.is_(True),
        ).count()
    
    def get_duty_counts_by_type(self):
        """Get count of duties by type for finalized schedules only"""
        from sqlalchemy import func
        duty_counts = db.session.query(
            DutyType.name,
            func.count(DutyAssignment.id).label('count')
        ).join(
            DutyAssignment, DutyType.id == DutyAssignment.duty_type_id
        ).join(
            DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
        ).filter(
            DutyAssignment.soldier_id == self.id,
            DutySchedule.is_finalized == True
        ).group_by(DutyType.name).all()
        
        return {duty_type: count for duty_type, count in duty_counts}
    
    def get_total_finalized_duties(self):
        """Get total number of finalized duties"""
        return db.session.query(DutyAssignment).join(
            DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
        ).filter(
            DutyAssignment.soldier_id == self.id,
            DutySchedule.is_finalized == True
        ).count()
    
    def get_duty_history(self):
        """Get complete duty history for finalized schedules"""
        return db.session.query(DutyAssignment).join(
            DutyType, DutyType.id == DutyAssignment.duty_type_id
        ).join(
            DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
        ).filter(
            DutyAssignment.soldier_id == self.id,
            DutySchedule.is_finalized == True
        ).order_by(DutyAssignment.duty_date.desc()).all()
    
    def get_last_duty_date(self):
        """Get the date of the last duty assignment (finalized schedules only)"""
        last_assignment = db.session.query(DutyAssignment).join(
            DutySchedule, DutySchedule.schedule_date == DutyAssignment.duty_date
        ).filter(
            DutyAssignment.soldier_id == self.id,
            DutySchedule.is_finalized == True
        ).order_by(DutyAssignment.duty_date.desc()).first()
        
        return last_assignment.duty_date if last_assignment else None

class DutyType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    # Retained for database compatibility. Staffing is now configured per
    # service number through DutyNumberRequirement.
    team_size = db.Column(db.Integer, default=1)
    shifts_per_day = db.Column(db.Integer, default=3)
    is_active = db.Column(db.Boolean, default=True)
    requires_weapon = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    duty_assignments = db.relationship('DutyAssignment', backref='duty_type', lazy=True)
    service_shifts = db.relationship(
        'DutyServiceShift', backref='duty_type', lazy=True,
        cascade='all, delete-orphan', order_by='DutyServiceShift.sequence'
    )
    number_requirements = db.relationship(
        'DutyNumberRequirement', backref='duty_type', lazy=True,
        cascade='all, delete-orphan', order_by='DutyNumberRequirement.service_number'
    )

    def get_service_numbers(self):
        numbers = [requirement.service_number for requirement in self.number_requirements]
        if not numbers:
            numbers = sorted({shift.service_number for shift in self.service_shifts})
        return numbers or [1, 2, 3]

    def get_staff_count(self, service_number):
        requirement = next(
            (
                requirement for requirement in self.number_requirements
                if requirement.service_number == service_number
            ),
            None,
        )
        return requirement.staff_count if requirement else 1

    def get_shifts_for_number(self, service_number):
        from service_numbers import ServiceShift, get_service_number_shifts

        configured = [
            ServiceShift(shift.start_time, shift.end_time)
            for shift in self.service_shifts
            if shift.service_number == service_number
        ]
        if configured:
            return tuple(configured)
        # No rows at all means a legacy/new in-memory duty that still uses the
        # canonical default. Missing rows on a configured duty mean disabled.
        if not self.service_shifts:
            return get_service_number_shifts(service_number)
        return ()
    
    def __repr__(self):
        return f'<DutyType {self.name}>'


class DutyNumberRequirement(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            'duty_type_id', 'service_number',
            name='uq_duty_number_requirement',
        ),
        db.CheckConstraint('service_number > 0', name='ck_duty_number_positive'),
        db.CheckConstraint('staff_count > 0', name='ck_duty_staff_count_positive'),
    )

    id = db.Column(db.Integer, primary_key=True)
    duty_type_id = db.Column(
        db.Integer, db.ForeignKey('duty_type.id'), nullable=False, index=True
    )
    service_number = db.Column(db.Integer, nullable=False)
    staff_count = db.Column(db.Integer, nullable=False, default=1)

    def __repr__(self):
        return (
            f'<DutyNumberRequirement {self.duty_type.name} '
            f'No {self.service_number} x{self.staff_count}>'
        )


class DutyServiceShift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    duty_type_id = db.Column(
        db.Integer, db.ForeignKey('duty_type.id'), nullable=False, index=True
    )
    service_number = db.Column(db.Integer, nullable=False)
    start_time = db.Column(db.String(5), nullable=False)
    end_time = db.Column(db.String(5), nullable=False)
    sequence = db.Column(db.Integer, nullable=False, default=0)

    def __repr__(self):
        return (
            f'<DutyServiceShift {self.duty_type.name} No {self.service_number} '
            f'{self.start_time}-{self.end_time}>'
        )

class DutyAssignment(db.Model):
    __table_args__ = (
        db.UniqueConstraint(
            'soldier_id', 'duty_date', name='uq_duty_assignment_soldier_date'
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    soldier_id = db.Column(db.Integer, db.ForeignKey('soldier.id'), nullable=False)
    duty_type_id = db.Column(db.Integer, db.ForeignKey('duty_type.id'), nullable=False)
    duty_date = db.Column(db.Date, nullable=False)
    service_number = db.Column(db.Integer, nullable=False, default=1)
    position_in_team = db.Column(db.Integer, default=1)  # For team-based duties
    shift_snapshot = db.Column(db.Text)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DutyAssignment {self.soldier.name} - {self.duty_type.name}>'
    
    def get_service_shifts(self):
        """Return the immutable assigned hours, or the current duty configuration."""
        from service_numbers import deserialize_service_shifts

        snapshot = deserialize_service_shifts(self.shift_snapshot)
        if snapshot:
            return snapshot
        return self.duty_type.get_shifts_for_number(self.service_number)

    def get_shift_occurrences(self):
        """Return date-aware periods for this operational duty day."""
        from service_numbers import get_shift_occurrences_for_shifts
        return get_shift_occurrences_for_shifts(
            self.duty_date, self.get_service_shifts()
        )

class DutySchedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    schedule_date = db.Column(db.Date, nullable=False, unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    is_finalized = db.Column(db.Boolean, default=False)
    
    def __repr__(self):
        return f'<DutySchedule {self.schedule_date}>'

class Equipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    serial_number = db.Column(db.String(50), unique=True)
    equipment_type = db.Column(db.String(50), nullable=False)  # Όπλο, Ρούχα, Εξοπλισμός, κλπ
    status = db.Column(db.String(20), default='Available')  # Available, Assigned, Maintenance, Lost
    assigned_to = db.Column(db.Integer, db.ForeignKey('soldier.id'), nullable=True)
    assigned_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationship
    soldier = db.relationship('Soldier', backref='equipment_assignments')
    
    def __repr__(self):
        return f'<Equipment {self.name} - {self.serial_number}>'

class SoldierLeave(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    soldier_id = db.Column(db.Integer, db.ForeignKey('soldier.id'), nullable=False)
    leave_type = db.Column(db.String(50), nullable=False)  # Κανονική, Ασθένεια, Εκτακτη, κλπ
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    days_count = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pending')  # Pending, Approved, Rejected
    approved_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    approved_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Relationships
    soldier = db.relationship('Soldier', backref='leaves')
    approver = db.relationship('User', backref='approved_leaves')
    
    def __repr__(self):
        return f'<SoldierLeave {self.soldier.name} - {self.leave_type}>'
    
    def is_active(self):
        """Check if leave is currently active"""
        return self.status == 'Approved' and self.start_date <= date.today() <= self.end_date


class MedicalCase(db.Model):
    """A period during which a soldier is sick or staying at the infirmary."""

    id = db.Column(db.Integer, primary_key=True)
    soldier_id = db.Column(db.Integer, db.ForeignKey('soldier.id'), nullable=False)
    illness = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(20), nullable=False)  # Battalion, Infirmary
    attends_roll_call = db.Column(db.Boolean, nullable=False, default=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    soldier = db.relationship('Soldier', backref='medical_cases')
    creator = db.relationship('User', backref='created_medical_cases')

    def is_active_on(self, target_date=None):
        target_date = target_date or date.today()
        return self.start_date <= target_date and (
            self.end_date is None or self.end_date >= target_date
        )

    @property
    def report_status(self):
        if self.location == 'Infirmary':
            return 'Δεν συμμετέχει — Ιατρείο'
        if self.attends_roll_call:
            return 'Παρουσιάζεται στην αναφορά — Τάγμα'
        return 'Δεν συμμετέχει — Ασθενής στο Τάγμα'

    def __repr__(self):
        return f'<MedicalCase {self.soldier.name} - {self.illness}>'

class StaffingAlert(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    alert_date = db.Column(db.Date, nullable=False)
    duty_type_id = db.Column(db.Integer, db.ForeignKey('duty_type.id'), nullable=False)
    required_staff = db.Column(db.Integer, nullable=False)
    available_staff = db.Column(db.Integer, nullable=False)
    shortage = db.Column(db.Integer, nullable=False)
    severity = db.Column(db.String(20), default='Medium')  # Low, Medium, High, Critical
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text)
    
    # Relationship
    duty_type = db.relationship('DutyType', backref='staffing_alerts')
    
    def __repr__(self):
        return f'<StaffingAlert {self.duty_type.name} - {self.alert_date}>'
