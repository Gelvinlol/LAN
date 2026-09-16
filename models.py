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

    @property
    def is_active(self):
        return bool(self.active)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_commander(self):
        return self.role == "Διοικητής"
    
    def can_view_logs(self):
        return self.role == "Διοικητής"
    
    def __repr__(self):
        return f'<User {self.username}>'

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
    team_size = db.Column(db.Integer, default=1)
    shifts_per_day = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    duty_assignments = db.relationship('DutyAssignment', backref='duty_type', lazy=True)
    time_slots = db.relationship('DutyTimeSlot', backref='duty_type', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<DutyType {self.name}>'

class DutyTimeSlot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    duty_type_id = db.Column(db.Integer, db.ForeignKey('duty_type.id'), nullable=False)
    shift_number = db.Column(db.Integer, nullable=False)  # 1, 2, 3 for different shifts
    start_time = db.Column(db.String(5), nullable=False)  # Format: "HH:MM"
    end_time = db.Column(db.String(5), nullable=False)    # Format: "HH:MM"
    
    def __repr__(self):
        return f'<DutyTimeSlot {self.duty_type.name} Shift {self.shift_number}>'

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
    shift_number = db.Column(db.Integer, default=1)
    position_in_team = db.Column(db.Integer, default=1)  # For team-based duties
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<DutyAssignment {self.soldier.name} - {self.duty_type.name}>'
    
    def get_time_slot(self):
        """Get the time slot for this duty assignment"""
        return DutyTimeSlot.query.filter_by(
            duty_type_id=self.duty_type_id,
            shift_number=self.shift_number
        ).first()

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
