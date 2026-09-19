from flask import render_template, request, redirect, url_for, flash, make_response, session
from datetime import datetime, date, timedelta
from app import app, db
from models import Soldier, DutyType, DutyNumberRequirement, DutyServiceShift, DutyAssignment, DutySchedule, User, UserPermission, UnitSettings, ActivityLog, Equipment, SoldierLeave, MedicalCase, StaffingAlert
from simple_scheduler import SimpleScheduler
from service_numbers import SERVICE_NUMBER_SHIFTS
from reporting import build_fairness_report
from permissions import ALL_PERMISSION_KEYS, ENDPOINT_PERMISSIONS, PERMISSION_GROUPS
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from urllib.parse import urljoin, urlparse
import logging


@app.context_processor
def inject_unit_identity():
    """Expose the singleton unit identity to the shared navigation."""
    return {'unit_identity': db.session.get(UnitSettings, 1)}


@app.before_request
def enforce_account_permissions():
    """Apply module permissions consistently to page and mutation routes."""
    if not current_user.is_authenticated:
        return None
    required_permission = ENDPOINT_PERMISSIONS.get(request.endpoint)
    if required_permission and not current_user.has_permission(required_permission):
        flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή την ενότητα.', 'error')
        return redirect(url_for('index'))
    return None


def is_safe_redirect(target):
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return redirect_url.scheme in ("http", "https") and host_url.netloc == redirect_url.netloc

def log_activity(action, target_type=None, target_id=None, description=None):
    """Log user activity"""
    if current_user.is_authenticated:
        log = ActivityLog(
            user_id=current_user.id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description,
            ip_address=request.remote_addr
        )
        db.session.add(log)
        db.session.commit()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.is_active and user.check_password(password):
            login_user(user)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            log_activity('login', description=f'User {username} logged in')
            
            next_page = request.args.get('next')
            flash(f'Καλώς ήρθατε, {user.full_name}!', 'success')
            return redirect(next_page) if next_page and is_safe_redirect(next_page) else redirect(url_for('index'))
        else:
            flash('Λανθασμένα στοιχεία σύνδεσης.', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    log_activity('logout', description=f'User {current_user.username} logged out')
    logout_user()
    flash('Αποσυνδεθήκατε με επιτυχία.', 'info')
    return redirect(url_for('login'))

@app.route('/logs')
@login_required
def view_logs():
    if not current_user.can_view_logs():
        flash('Δεν έχετε δικαίωμα πρόσβασης σε αυτή τη σελίδα.', 'error')
        return redirect(url_for('index'))
    
    page = request.args.get('page', 1, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).paginate(
        page=page, per_page=50, error_out=False
    )
    
    return render_template('logs.html', logs=logs)


@app.route('/unit-settings', methods=['GET', 'POST'])
@login_required
def unit_settings():
    if not current_user.is_commander():
        flash('Μόνο ο Διοικητής μπορεί να διαχειριστεί τα στοιχεία της μονάδας.', 'error')
        return redirect(url_for('index'))

    settings = db.session.get(UnitSettings, 1)
    if request.method == 'POST':
        def field(name, max_length):
            return request.form.get(name, '').strip()[:max_length]

        camp_name = field('camp_name', 150)
        unit_name = field('unit_name', 150)
        battalion_name = field('battalion_name', 150)
        branch = field('branch', 100)
        if not all((camp_name, unit_name, battalion_name, branch)):
            flash(
                'Στρατόπεδο, μονάδα, τάγμα και Όπλο/Σώμα είναι υποχρεωτικά.',
                'error',
            )
        else:
            if settings is None:
                settings = UnitSettings(id=1)
                db.session.add(settings)
            settings.camp_name = camp_name
            settings.unit_name = unit_name
            settings.battalion_name = battalion_name
            settings.branch = branch
            settings.formation_name = field('formation_name', 150)
            settings.unit_code = field('unit_code', 50)
            settings.location = field('location', 200)
            settings.commander_rank = field('commander_rank', 80)
            settings.commander_name = field('commander_name', 120)
            settings.contact_phone = field('contact_phone', 30)
            settings.contact_email = field('contact_email', 120)
            settings.motto = field('motto', 200)
            settings.notes = request.form.get('notes', '').strip()[:2000]
            settings.updated_by = current_user.id
            settings.updated_at = datetime.utcnow()
            db.session.commit()
            log_activity(
                'update_unit_settings', 'unit_settings', settings.id,
                'Ενημερώθηκαν τα διοικητικά στοιχεία της μονάδας.'
            )
            flash('Τα στοιχεία της μονάδας αποθηκεύτηκαν.', 'success')
            return redirect(url_for('unit_settings'))

    return render_template('unit_settings.html', settings=settings)


def _commander_only():
    if current_user.is_commander():
        return None
    flash('Μόνο ο Διοικητής μπορεί να διαχειριστεί λογαριασμούς.', 'error')
    return redirect(url_for('index'))


def _replace_user_permissions(user, submitted_permissions):
    valid_permissions = set(submitted_permissions) & set(ALL_PERMISSION_KEYS)
    user.permissions.clear()
    user.permissions.extend(
        UserPermission(permission_key=permission_key)
        for permission_key in sorted(valid_permissions)
    )


@app.route('/accounts')
@login_required
def accounts():
    denied = _commander_only()
    if denied:
        return denied
    users = User.query.order_by(User.active.desc(), User.full_name, User.username).all()
    return render_template(
        'accounts.html', users=users, permission_groups=PERMISSION_GROUPS
    )


@app.route('/accounts/new', methods=['GET', 'POST'])
@login_required
def create_account():
    denied = _commander_only()
    if denied:
        return denied
    if request.method == 'POST':
        username = request.form.get('username', '').strip()[:80]
        full_name = request.form.get('full_name', '').strip()[:100]
        role = request.form.get('role', '').strip()[:50]
        password = request.form.get('password', '')
        if not username or not full_name or not role:
            flash('Όνομα χρήστη, ονομασία λογαριασμού και ρόλος είναι υποχρεωτικά.', 'error')
        elif len(password) < 8:
            flash('Ο κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες.', 'error')
        elif User.query.filter(db.func.lower(User.username) == username.lower()).first():
            flash('Το όνομα χρήστη χρησιμοποιείται ήδη.', 'error')
        else:
            user = User(
                username=username,
                full_name=full_name,
                role=role,
                password_hash=generate_password_hash(password),
                active=True,
            )
            _replace_user_permissions(user, request.form.getlist('permissions'))
            db.session.add(user)
            db.session.commit()
            log_activity(
                'create_account', 'user', user.id,
                f'Δημιουργήθηκε ο λογαριασμός {user.username} ({user.role}).'
            )
            flash(f'Ο λογαριασμός {user.username} δημιουργήθηκε.', 'success')
            return redirect(url_for('accounts'))
    return render_template(
        'account_form.html', account=None,
        permission_groups=PERMISSION_GROUPS, selected_permissions=set()
    )


@app.route('/accounts/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_account(user_id):
    denied = _commander_only()
    if denied:
        return denied
    account = db.get_or_404(User, user_id)
    if request.method == 'POST':
        username = request.form.get('username', '').strip()[:80]
        full_name = request.form.get('full_name', '').strip()[:100]
        role = request.form.get('role', '').strip()[:50]
        if account.id == current_user.id:
            role = account.role
        duplicate = User.query.filter(
            db.func.lower(User.username) == username.lower(), User.id != account.id
        ).first()
        if not username or not full_name or not role:
            flash('Όνομα χρήστη, ονομασία λογαριασμού και ρόλος είναι υποχρεωτικά.', 'error')
        elif duplicate:
            flash('Το όνομα χρήστη χρησιμοποιείται ήδη.', 'error')
        else:
            account.username = username
            account.full_name = full_name
            if account.id != current_user.id:
                account.role = role
                account.active = request.form.get('active') == 'yes'
            else:
                account.active = True
            password = request.form.get('password', '')
            if password:
                if len(password) < 8:
                    flash('Ο νέος κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες.', 'error')
                    return render_template(
                        'account_form.html', account=account,
                        permission_groups=PERMISSION_GROUPS,
                        selected_permissions={
                            permission.permission_key for permission in account.permissions
                        },
                    )
                account.password_hash = generate_password_hash(password)
            _replace_user_permissions(account, request.form.getlist('permissions'))
            db.session.commit()
            log_activity(
                'update_account', 'user', account.id,
                f'Ενημερώθηκε ο λογαριασμός {account.username} ({account.role}).'
            )
            flash(f'Ο λογαριασμός {account.username} ενημερώθηκε.', 'success')
            return redirect(url_for('accounts'))

    selected_permissions = {
        permission.permission_key for permission in account.permissions
    }
    return render_template(
        'account_form.html', account=account,
        permission_groups=PERMISSION_GROUPS,
        selected_permissions=selected_permissions,
    )

@app.route('/')
@login_required
def index():
    # Get overview statistics
    total_soldiers = Soldier.query.count()
    active_soldiers = Soldier.query.filter_by(status='Active').count()
    soldiers_on_leave = Soldier.query.filter_by(status='On Leave').count()
    total_duty_types = DutyType.query.filter_by(is_active=True).count()
    
    # Get today's duties
    today = date.today()
    today_duties = db.session.query(DutyAssignment, Soldier, DutyType).join(
        Soldier, DutyAssignment.soldier_id == Soldier.id
    ).join(
        DutyType, DutyAssignment.duty_type_id == DutyType.id
    ).filter(
        DutyAssignment.duty_date == today
    ).order_by(DutyType.name, DutyAssignment.service_number).all()
    
    # Get new statistics
    total_equipment = Equipment.query.count()
    assigned_equipment = Equipment.query.filter_by(status='Assigned').count()
    active_leaves_today = SoldierLeave.query.filter(
        SoldierLeave.status == 'Approved',
        SoldierLeave.start_date <= today,
        SoldierLeave.end_date >= today
    ).count()
    pending_leaves = SoldierLeave.query.filter_by(status='Pending').count()
    active_alerts = StaffingAlert.query.filter_by(resolved=False).count()
    
    stats = {
        'total_soldiers': total_soldiers,
        'active_soldiers': active_soldiers,
        'soldiers_on_leave': soldiers_on_leave,
        'total_duty_types': total_duty_types,
        'total_equipment': total_equipment,
        'assigned_equipment': assigned_equipment,
        'active_leaves_today': active_leaves_today,
        'pending_leaves': pending_leaves,
        'active_alerts': active_alerts
    }
    
    return render_template('index.html', stats=stats, today_duties=today_duties, today=today)

@app.route('/soldiers')
@login_required
def soldiers():
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    
    query = Soldier.query
    
    if search:
        query = query.filter(
            db.or_(
                Soldier.name.contains(search),
                Soldier.military_id.contains(search),
                Soldier.specialty.contains(search)
            )
        )
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    soldiers_list = query.order_by(Soldier.name).all()
    
    return render_template('soldiers.html', soldiers=soldiers_list, search=search, status_filter=status_filter)

@app.route('/soldiers/add', methods=['GET'])
@login_required
def add_soldier():
    return render_template('soldier_interview.html')

@app.route('/soldiers/add_interview', methods=['POST'])
@login_required
def add_soldier_interview():
    try:
        soldier = Soldier()
        
        # Basic information
        soldier.name = request.form['name']
        soldier.military_id = request.form['military_id']
        soldier.enlistment_date = datetime.strptime(request.form['enlistment_date'], '%Y-%m-%d').date()
        soldier.specialty = request.form.get('specialty', '')
        soldier.category = request.form.get('category', '')
        soldier.medical_category = request.form.get('medical_category', '')
        
        # Birth date
        if request.form.get('birth_date'):
            soldier.birth_date = datetime.strptime(request.form['birth_date'], '%Y-%m-%d').date()
        
        # Family information
        soldier.father_name = request.form.get('father_name', '')
        soldier.mother_name = request.form.get('mother_name', '')
        soldier.father_profession = request.form.get('father_profession', '')
        soldier.mother_profession = request.form.get('mother_profession', '')
        soldier.profession = request.form.get('profession', '')
        
        # Siblings
        soldier.brothers_count = int(request.form.get('brothers_count', 0))
        soldier.sisters_count = int(request.form.get('sisters_count', 0))
        
        # Contact & residence information
        soldier.residence_address = request.form.get('residence_address', '')
        soldier.residence_city = request.form.get('residence_city', '')
        soldier.residence_prefecture = request.form.get('residence_prefecture', '')
        soldier.personal_phone = request.form.get('personal_phone', '')
        soldier.parents_phone = request.form.get('parents_phone', '')
        soldier.email = request.form.get('email', '')
        soldier.parent_email = request.form.get('parent_email', '')
        
        # Education & skills
        soldier.education = request.form.get('education', '')
        soldier.special_skills = request.form.get('special_skills', '')
        
        # Financial information
        soldier.amka = request.form.get('amka', '')
        soldier.tax_number = request.form.get('tax_number', '')
        soldier.iban = request.form.get('iban', '')
        soldier.bank = request.form.get('bank', '')
        
        # Interview notes
        soldier.interview_notes = request.form.get('interview_notes', '')
        
        # Validate IBAN length if provided
        if soldier.iban and len(soldier.iban) != 27:
            flash('ΙΒΑΝ πρέπει να είναι 27 χαρακτήρες', 'error')
            return render_template('soldier_interview.html')
        
        # Validate AMKA length if provided
        if soldier.amka and len(soldier.amka) != 11:
            flash('ΑΜΚΑ πρέπει να είναι 11 ψηφία', 'error')
            return render_template('soldier_interview.html')
        
        db.session.add(soldier)
        db.session.commit()
        
        log_activity('add_soldier_interview', 'soldier', soldier.id, 
                    f'Added new soldier with complete interview: {soldier.name}')
        flash(f'Η συνέντευξη για τον στρατιώτη {soldier.name} καταχωρήθηκε επιτυχώς!', 'success')
        return redirect(url_for('soldiers'))
        
    except ValueError as e:
        flash(f'Λάθος στην εισαγωγή δεδομένων: {str(e)}', 'error')
        db.session.rollback()
        return render_template('soldier_interview.html')
    except Exception as e:
        flash(f'Σφάλμα κατά την προσθήκη στρατιώτη: {str(e)}', 'error')
        db.session.rollback()
        return render_template('soldier_interview.html')

@app.route('/soldiers/<int:soldier_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_soldier(soldier_id):
    soldier = Soldier.query.get_or_404(soldier_id)
    
    if request.method == 'POST':
        try:
            soldier.name = request.form['name']
            soldier.military_id = request.form['military_id']
            soldier.enlistment_date = datetime.strptime(request.form['enlistment_date'], '%Y-%m-%d').date()
            soldier.specialty = request.form.get('specialty', '')
            soldier.medical_category = request.form.get('medical_category', '')
            soldier.status = request.form.get('status', 'Active')
            soldier.exemption_no_duty = bool(request.form.get('exemption_no_duty'))
            soldier.exemption_no_shaving = bool(request.form.get('exemption_no_shaving'))
            soldier.exemption_no_boots = bool(request.form.get('exemption_no_boots'))
            
            db.session.commit()
            flash(f'Soldier {soldier.name} updated successfully!', 'success')
            return redirect(url_for('soldiers'))
            
        except Exception as e:
            flash(f'Error updating soldier: {str(e)}', 'error')
            db.session.rollback()
    
    return render_template('edit_soldier.html', soldier=soldier)

@app.route('/soldiers/<int:soldier_id>/delete', methods=['POST'])
@login_required
def delete_soldier(soldier_id):
    soldier = Soldier.query.get_or_404(soldier_id)
    try:
        db.session.delete(soldier)
        db.session.commit()
        flash(f'Soldier {soldier.name} deleted successfully!', 'success')
    except Exception as e:
        flash(f'Error deleting soldier: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('soldiers'))

@app.route('/soldiers/<int:soldier_id>/history')
@login_required
def soldier_history(soldier_id):
    soldier = db.get_or_404(Soldier, soldier_id)
    duty_history = soldier.get_duty_history()
    duty_counts = soldier.get_duty_counts_by_type()
    total_duties = soldier.get_total_finalized_duties()
    
    return render_template('soldier_history.html', 
                         soldier=soldier, 
                         duty_history=duty_history,
                         duty_counts=duty_counts,
                         total_duties=total_duties)

@app.route('/soldiers/<int:soldier_id>/update_ey', methods=['POST'])
@login_required
def update_soldier_ey(soldier_id):
    soldier = Soldier.query.get_or_404(soldier_id)
    
    try:
        soldier.days_out_of_service = int(request.form.get('days_out_of_service', 0))
        soldier.out_of_service_reason = request.form.get('out_of_service_reason', '')
        
        db.session.commit()
        
        log_activity('update_soldier_ey', 'soldier', soldier.id, 
                    f'Updated ΕΥ status: {soldier.days_out_of_service} days - {soldier.out_of_service_reason}')
        
        flash(f'Updated ΕΥ status for {soldier.name}', 'success')
    except Exception as e:
        flash(f'Error updating ΕΥ status: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('soldiers'))

@app.route('/soldiers/<int:soldier_id>/profile')
@login_required
def soldier_profile(soldier_id):
    soldier = Soldier.query.get_or_404(soldier_id)
    return render_template('soldier_profile.html', soldier=soldier)


def _assignment_ineligibility(soldier, duty_type, duty_date, assignment_id=None):
    if not soldier.is_available_for_duty():
        return 'Ο στρατιώτης δεν είναι διαθέσιμος για υπηρεσία.'
    if duty_type.requires_weapon and not soldier.is_available_for_armed_duty():
        return 'Η υπηρεσία απαιτεί όπλο. Επιτρέπονται μόνο Ι1, Ι2 και Ι3 Ένοπλο.'
    leave = SoldierLeave.query.filter(
        SoldierLeave.soldier_id == soldier.id,
        SoldierLeave.status == 'Approved',
        SoldierLeave.start_date <= duty_date,
        SoldierLeave.end_date >= duty_date,
    ).first()
    if leave:
        return 'Ο στρατιώτης βρίσκεται σε εγκεκριμένη άδεια.'
    medical_case = MedicalCase.query.filter(
        MedicalCase.soldier_id == soldier.id,
        MedicalCase.start_date <= duty_date,
        db.or_(MedicalCase.end_date.is_(None), MedicalCase.end_date >= duty_date),
    ).first()
    if medical_case:
        return f'Ο στρατιώτης έχει ενεργό περιστατικό ιατρείου ({medical_case.illness}).'
    existing = DutyAssignment.query.filter(
        DutyAssignment.duty_date == duty_date,
        DutyAssignment.soldier_id == soldier.id,
        DutyAssignment.id != assignment_id,
    ).first()
    if existing:
        return f'Ο στρατιώτης έχει ήδη τοποθετηθεί στην υπηρεσία {existing.duty_type.name}.'
    return None

@app.route('/schedule/edit_assignment/<int:assignment_id>', methods=['POST'])
@login_required
def edit_assignment(assignment_id):
    assignment = db.get_or_404(DutyAssignment, assignment_id)
    
    # Debug logging
    print(f"DEBUG: Editing assignment {assignment_id}")
    print(f"DEBUG: Form data: {dict(request.form)}")
    print(f"DEBUG: Current soldier: {assignment.soldier.name} (ID: {assignment.soldier_id})")
    
    # Check if schedule is not finalized
    schedule = DutySchedule.query.filter_by(schedule_date=assignment.duty_date).first()
    if schedule and schedule.is_finalized:
        flash('Cannot edit assignments in a finalized schedule', 'error')
        return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))
    
    try:
        new_soldier_id_str = request.form.get('soldier_id')
        if not new_soldier_id_str:
            flash('No soldier selected', 'error')
            return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))
            
        new_soldier_id = int(new_soldier_id_str)
        new_soldier = db.get_or_404(Soldier, new_soldier_id)
        
        # Check if it's actually a different soldier
        if assignment.soldier_id == new_soldier_id:
            flash('Same soldier selected - no change needed', 'info')
            return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))

        ineligibility = _assignment_ineligibility(
            new_soldier, assignment.duty_type, assignment.duty_date, assignment.id
        )
        if ineligibility:
            flash(ineligibility, 'error')
            return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))

        active_medical_case = MedicalCase.query.filter(
            MedicalCase.soldier_id == new_soldier_id,
            MedicalCase.start_date <= assignment.duty_date,
            db.or_(
                MedicalCase.end_date.is_(None),
                MedicalCase.end_date >= assignment.duty_date,
            ),
        ).first()
        if active_medical_case:
            flash(
                f'Ο {new_soldier.name} είναι καταχωρημένος ως ασθενής '
                f'({active_medical_case.illness}) για αυτή την ημερομηνία.',
                'error',
            )
            return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))

        existing_assignment = DutyAssignment.query.filter(
            DutyAssignment.duty_date == assignment.duty_date,
            DutyAssignment.soldier_id == new_soldier_id,
            DutyAssignment.id != assignment.id,
        ).first()
        if existing_assignment:
            flash(
                f'Ο {new_soldier.name} έχει ήδη τοποθετηθεί στην υπηρεσία '
                f'{existing_assignment.duty_type.name} για αυτή την ημερομηνία.',
                'error',
            )
            return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))
        
        old_soldier_name = assignment.soldier.name
        assignment.soldier_id = new_soldier_id
        assignment.notes = (
            f'Χειροκίνητη αλλαγή από {current_user.full_name} '
            f'({current_user.username}): {old_soldier_name} → {new_soldier.name}'
        )
        
        db.session.commit()
        
        log_activity('edit_assignment', 'duty_assignment', assignment.id, 
                    f'Changed soldier from {old_soldier_name} to {new_soldier.name}')
        
        flash(f'Assignment updated: {new_soldier.name} assigned to {assignment.duty_type.name}', 'success')
    except ValueError:
        flash('Invalid soldier ID', 'error')
    except Exception as e:
        flash(f'Error updating assignment: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('schedule', date=assignment.duty_date.strftime('%Y-%m-%d')))


@app.route('/schedule/assignment/<int:assignment_id>/replacement')
@login_required
def replacement_candidates(assignment_id):
    assignment = db.get_or_404(DutyAssignment, assignment_id)
    scheduler = SimpleScheduler()
    candidates = scheduler.get_replacement_candidates(assignment)
    candidate_rows = [
        {
            'soldier': soldier,
            'total_duties': soldier.get_total_finalized_duties(),
            'special_duties': scheduler.get_special_day_count(soldier.id),
            'last_duty': soldier.get_last_duty_date(),
        }
        for soldier in candidates
    ]
    return render_template(
        'replacement_candidates.html', assignment=assignment,
        candidate_rows=candidate_rows,
    )


@app.route('/schedule/assignment/<int:assignment_id>/replace', methods=['POST'])
@login_required
def replace_assignment_emergency(assignment_id):
    assignment = db.get_or_404(DutyAssignment, assignment_id)
    reason = request.form.get('reason', '').strip()[:300]
    try:
        soldier_id = int(request.form.get('soldier_id', ''))
    except ValueError:
        soldier_id = 0
    if not reason:
        flash('Καταχωρίστε την αιτία της έκτακτης αντικατάστασης.', 'error')
        return redirect(url_for('replacement_candidates', assignment_id=assignment.id))

    scheduler = SimpleScheduler()
    eligible_ids = {
        soldier.id for soldier in scheduler.get_replacement_candidates(assignment)
    }
    if soldier_id not in eligible_ids:
        flash('Ο επιλεγμένος στρατιώτης δεν είναι πλέον διαθέσιμος ή κατάλληλος.', 'error')
        return redirect(url_for('replacement_candidates', assignment_id=assignment.id))

    replacement = db.get_or_404(Soldier, soldier_id)
    old_soldier_name = assignment.soldier.name
    assignment.soldier_id = replacement.id
    assignment.notes = (
        f'Έκτακτη αντικατάσταση από {current_user.full_name} '
        f'({current_user.username}): {old_soldier_name} → {replacement.name}. '
        f'Αιτία: {reason}'
    )
    db.session.commit()
    log_activity(
        'emergency_replacement', 'duty_assignment', assignment.id,
        f'{old_soldier_name} → {replacement.name}. Αιτία: {reason}'
    )
    flash(f'Η αντικατάσταση με τον {replacement.name} ολοκληρώθηκε.', 'success')
    return redirect(url_for('schedule', date=assignment.duty_date.isoformat()))

@app.route('/duties')
@login_required
def duties():
    duty_types = DutyType.query.filter_by(is_active=True).all()
    return render_template('duties.html', duty_types=duty_types)

@app.route('/duties/<int:duty_id>/edit', methods=['GET'])
@login_required
def get_duty_type(duty_id):
    """Get duty type data for editing"""
    from flask import jsonify
    duty_type = DutyType.query.get_or_404(duty_id)
    return jsonify({
        'id': duty_type.id,
        'name': duty_type.name,
        'description': duty_type.description,
        'is_active': duty_type.is_active,
        'requires_weapon': duty_type.requires_weapon,
    })

@app.route('/duties/<int:duty_id>/toggle', methods=['POST'])
@login_required
def toggle_duty_type(duty_id):
    """Toggle duty type active status"""
    from flask import jsonify
    try:
        duty_type = DutyType.query.get_or_404(duty_id)
        duty_type.is_active = not duty_type.is_active
        db.session.commit()
        
        action = 'activated' if duty_type.is_active else 'deactivated'
        log_activity('toggle_duty_type', 'duty_type', duty_type.id, 
                    f'Duty type {duty_type.name} {action}')
        
        return jsonify({'success': True, 'is_active': duty_type.is_active})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/duties/edit', methods=['POST'])
@login_required
def edit_duty_type():
    """Edit existing duty type"""
    try:
        duty_id = int(request.form['duty_id'])
        duty_type = DutyType.query.get_or_404(duty_id)
        
        old_name = duty_type.name
        duty_type.name = request.form['name']
        duty_type.description = request.form.get('description', '')
        duty_type.requires_weapon = request.form.get('requires_weapon') == 'yes'
        duty_type.team_size = 1
        duty_type.shifts_per_day = 3
        
        db.session.commit()
        
        log_activity('edit_duty_type', 'duty_type', duty_type.id, 
                    f'Updated duty type from {old_name} to {duty_type.name}')
        
        flash(f'Η υπηρεσία {duty_type.name} ενημερώθηκε επιτυχώς!', 'success')
        
    except Exception as e:
        flash(f'Σφάλμα κατά την ενημέρωση υπηρεσίας: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('duties'))


@app.route('/duties/<int:duty_id>/numbers', methods=['GET', 'POST'])
@login_required
def configure_duty_numbers(duty_id):
    duty_type = db.get_or_404(DutyType, duty_id)

    if request.method == 'POST':
        try:
            configured = {}
            use_default = request.form.get('action') == 'reset-default'
            submitted_numbers = (
                ['1', '2', '3'] if use_default
                else request.form.getlist('service_number')
            )
            seen_numbers = set()
            for raw_number in submitted_numbers:
                service_number = int(raw_number)
                if service_number <= 0 or service_number in seen_numbers:
                    raise ValueError('Τα νούμερα πρέπει να είναι μοναδικοί θετικοί αριθμοί.')
                seen_numbers.add(service_number)
                if use_default:
                    configured[service_number] = [
                        1,
                        [
                            (shift.start, shift.end)
                            for shift in SERVICE_NUMBER_SHIFTS[service_number]
                        ],
                    ]
                    continue

                staff_count = int(
                    request.form.get(f'number_{service_number}_staff_count', '1')
                )
                if staff_count <= 0:
                    raise ValueError('Τα άτομα ανά νούμερο πρέπει να είναι τουλάχιστον ένα.')
                starts = request.form.getlist(f'number_{service_number}_start')
                ends = request.form.getlist(f'number_{service_number}_end')
                shifts = []
                for start, end in zip(starts, ends):
                    start = start.strip()
                    end = end.strip()
                    if not start and not end:
                        continue
                    datetime.strptime(start, '%H:%M')
                    datetime.strptime(end, '%H:%M')
                    if start == end:
                        raise ValueError(
                            f'Στο Νο {service_number} η έναρξη και η λήξη '
                            'δεν μπορούν να είναι ίδιες.'
                        )
                    shifts.append((start, end))
                if not shifts:
                    raise ValueError(
                        f'Το ενεργό Νο {service_number} χρειάζεται τουλάχιστον ένα ωράριο.'
                    )
                if len(shifts) != len(set(shifts)):
                    raise ValueError(f'Το Νο {service_number} περιέχει διπλό ωράριο.')
                configured[service_number] = [staff_count, shifts]

            if not configured:
                raise ValueError('Πρέπει να παραμείνει ενεργό τουλάχιστον ένα νούμερο.')

            DutyServiceShift.query.filter_by(duty_type_id=duty_type.id).delete()
            DutyNumberRequirement.query.filter_by(duty_type_id=duty_type.id).delete()
            for service_number, (staff_count, shifts) in configured.items():
                db.session.add(DutyNumberRequirement(
                    duty_type_id=duty_type.id,
                    service_number=service_number,
                    staff_count=staff_count,
                ))
                for sequence, (start, end) in enumerate(shifts):
                    db.session.add(DutyServiceShift(
                        duty_type_id=duty_type.id,
                        service_number=service_number,
                        start_time=start,
                        end_time=end,
                        sequence=sequence,
                    ))
            duty_type.shifts_per_day = len(configured)
            db.session.commit()
            log_activity(
                'configure_duty_numbers', 'duty_type', duty_type.id,
                f'Ενημερώθηκαν τα νούμερα και ωράρια της υπηρεσίας {duty_type.name}.'
            )
            flash(f'Τα ωράρια της υπηρεσίας {duty_type.name} αποθηκεύτηκαν.', 'success')
            return redirect(url_for('configure_duty_numbers', duty_id=duty_type.id))
        except (ValueError, TypeError):
            db.session.rollback()
            flash(
                'Ελέγξτε ότι κάθε ενεργό νούμερο έχει έγκυρα και διαφορετικά ωράρια.',
                'error',
            )
        except Exception as exc:
            db.session.rollback()
            logging.exception('Could not configure duty number hours')
            flash(f'Σφάλμα αποθήκευσης ωραρίων: {exc}', 'error')

    configured = [
        {
            'number': number,
            'staff_count': duty_type.get_staff_count(number),
            'shifts': duty_type.get_shifts_for_number(number),
        }
        for number in duty_type.get_service_numbers()
    ]
    return render_template(
        'duty_numbers.html', duty_type=duty_type, configured=configured
    )

@app.route('/duties/add', methods=['POST'])
@login_required
def add_duty_type():
    try:
        duty_type = DutyType(
            name=request.form['name'],
            description=request.form.get('description', ''),
            team_size=1,
            shifts_per_day=3,
            requires_weapon=request.form.get('requires_weapon') == 'yes',
        )
        
        db.session.add(duty_type)
        db.session.flush()
        for service_number, shifts in SERVICE_NUMBER_SHIFTS.items():
            db.session.add(DutyNumberRequirement(
                duty_type_id=duty_type.id,
                service_number=service_number,
                staff_count=1,
            ))
            for sequence, shift in enumerate(shifts):
                db.session.add(DutyServiceShift(
                    duty_type_id=duty_type.id,
                    service_number=service_number,
                    start_time=shift.start,
                    end_time=shift.end,
                    sequence=sequence,
                ))
        db.session.commit()
        flash(
            f'Η υπηρεσία {duty_type.name} δημιουργήθηκε. '
            'Ελέγξτε τώρα τα νούμερα και τα ωράριά της.',
            'success',
        )
        return redirect(url_for('configure_duty_numbers', duty_id=duty_type.id))
        
    except Exception as e:
        flash(f'Error adding duty type: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('duties'))

@app.route('/schedule')
@login_required
def schedule():
    selected_date = request.args.get('date')
    if selected_date:
        try:
            schedule_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            schedule_date = date.today()
    else:
        schedule_date = date.today()
    
    # Get existing assignments for the date
    assignments = db.session.query(DutyAssignment, Soldier, DutyType).join(
        Soldier, DutyAssignment.soldier_id == Soldier.id
    ).join(
        DutyType, DutyAssignment.duty_type_id == DutyType.id
    ).filter(
        DutyAssignment.duty_date == schedule_date
    ).order_by(DutyType.name, DutyAssignment.service_number).all()
    
    # Check if schedule exists for this date
    schedule_obj = DutySchedule.query.filter_by(schedule_date=schedule_date).first()
    
    # Get all available soldiers for dropdown (when editing assignments)
    medically_unavailable = db.session.query(MedicalCase.soldier_id).filter(
        MedicalCase.start_date <= schedule_date,
        db.or_(MedicalCase.end_date.is_(None), MedicalCase.end_date >= schedule_date),
    )
    available_soldiers = Soldier.query.filter(
        Soldier.status == 'Active',
        ~Soldier.id.in_(medically_unavailable),
    ).order_by(Soldier.name).all()
    assigned_soldier_ids = {
        assignment.soldier_id for assignment, _, _ in assignments
    }
    
    return render_template('schedule.html', 
                         assignments=assignments, 
                         schedule_date=schedule_date,
                         schedule_obj=schedule_obj,
                         available_soldiers=available_soldiers,
                         assigned_soldier_ids=assigned_soldier_ids)

@app.route('/schedule/generate', methods=['POST'])
@login_required
def generate_schedule():
    selected_date = request.form.get('date')
    if selected_date:
        try:
            schedule_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format', 'error')
            return redirect(url_for('schedule'))
    else:
        schedule_date = date.today()
    
    try:
        scheduler = SimpleScheduler()
        success = scheduler.generate_daily_schedule(schedule_date)
        
        if success:
            log_activity('generate_schedule', 'schedule', None, 
                        f'Generated schedule for {schedule_date.strftime("%d/%m/%Y")}')
            flash(f'Schedule generated successfully for {schedule_date}!', 'success')
        else:
            flash(
                'Το πρόγραμμα δημιουργήθηκε με κενές θέσεις επειδή δεν υπάρχουν '
                'αρκετά διαθέσιμα άτομα χωρίς δεύτερη υπηρεσία την ίδια ημέρα.',
                'warning',
            )
            
    except Exception as e:
        flash(f'Error generating schedule: {str(e)}', 'error')
        logging.error(f"Schedule generation error: {e}")
    
    return redirect(url_for('schedule', date=schedule_date.strftime('%Y-%m-%d')))

@app.route('/schedule/finalize', methods=['POST'])
@login_required
def finalize_schedule():
    selected_date = request.form.get('date')
    if selected_date:
        try:
            schedule_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format', 'error')
            return redirect(url_for('schedule'))
    else:
        schedule_date = date.today()
    
    try:
        # Find or create schedule record
        schedule_obj = DutySchedule.query.filter_by(schedule_date=schedule_date).first()
        if not schedule_obj:
            flash('No schedule found for this date', 'error')
            return redirect(url_for('schedule'))
        
        # Finalize the schedule
        schedule_obj.is_finalized = True
        db.session.commit()
        
        log_activity('finalize_schedule', 'schedule', schedule_obj.id, 
                    f'Finalized schedule for {schedule_date.strftime("%d/%m/%Y")}')
        
        flash(f'Schedule finalized for {schedule_date}! Duties are now official.', 'success')
        
    except Exception as e:
        flash(f'Error finalizing schedule: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('schedule', date=schedule_date.strftime('%Y-%m-%d')))

@app.route('/schedule/clear', methods=['POST'])
@login_required
def clear_schedule():
    selected_date = request.form.get('date')
    if selected_date:
        try:
            schedule_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format', 'error')
            return redirect(url_for('schedule'))
    else:
        schedule_date = date.today()
    
    try:
        # Clear all assignments for the date
        DutyAssignment.query.filter_by(duty_date=schedule_date).delete()
        
        # Remove schedule record
        schedule_obj = DutySchedule.query.filter_by(schedule_date=schedule_date).first()
        if schedule_obj:
            db.session.delete(schedule_obj)
        
        db.session.commit()
        flash(f'Schedule cleared for {schedule_date}!', 'success')
        
    except Exception as e:
        flash(f'Error clearing schedule: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('schedule', date=schedule_date.strftime('%Y-%m-%d')))

@app.route('/duty_sheet')
@login_required
def duty_sheet():
    selected_date = request.args.get('date')
    if selected_date:
        try:
            sheet_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            sheet_date = date.today()
    else:
        sheet_date = date.today()
    
    # Get all assignments for the date, organized by duty type and shift
    assignments = db.session.query(DutyAssignment, Soldier, DutyType).join(
        Soldier, DutyAssignment.soldier_id == Soldier.id
    ).join(
        DutyType, DutyAssignment.duty_type_id == DutyType.id
    ).filter(
        DutyAssignment.duty_date == sheet_date
    ).order_by(DutyType.name, DutyAssignment.service_number, DutyAssignment.id).all()
    
    # Organize assignments by duty type and service number. Historical records
    # can contain more than one person per number; new schedules contain one.
    organized_duties = {}
    for assignment, soldier, duty_type in assignments:
        if duty_type.name not in organized_duties:
            organized_duties[duty_type.name] = {}
        
        service_number = assignment.service_number
        if service_number not in organized_duties[duty_type.name]:
            organized_duties[duty_type.name][service_number] = []
        
        organized_duties[duty_type.name][service_number].append({
            'soldier': soldier,
            'assignment': assignment,
            'time_info': ' · '.join(
                shift.label for shift in assignment.get_service_shifts()
            ),
            'service_shifts': assignment.get_service_shifts(),
            'shift_occurrences': assignment.get_shift_occurrences(),
        })
    
    return render_template('duty_sheet.html', 
                         organized_duties=organized_duties,
                         sheet_date=sheet_date,
                         print_mode=request.args.get('print') == 'true')

@app.route('/duty_sheet/print')
@login_required
def print_duty_sheet():
    selected_date = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    return redirect(url_for('duty_sheet', date=selected_date, print='true'))

@app.route('/prints')
@login_required
def prints():
    from datetime import date
    return render_template('prints.html', date=date)


@app.route('/reports/fairness')
@login_required
def fairness_report():
    end_date = date.today()
    start_date = end_date - timedelta(days=89)
    try:
        if request.args.get('start_date'):
            start_date = datetime.strptime(
                request.args['start_date'], '%Y-%m-%d'
            ).date()
        if request.args.get('end_date'):
            end_date = datetime.strptime(
                request.args['end_date'], '%Y-%m-%d'
            ).date()
        if start_date > end_date:
            raise ValueError
    except ValueError:
        flash('Επιλέξτε έγκυρο χρονικό διάστημα.', 'error')
        return redirect(url_for('fairness_report'))

    report = build_fairness_report(start_date, end_date)
    return render_template(
        'fairness_report.html', report=report,
        start_date=start_date, end_date=end_date,
    )

@app.route('/prints/roster')
@login_required
def print_roster():
    selected_date = request.args.get('date')
    if selected_date:
        try:
            roster_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
        except ValueError:
            roster_date = date.today()
    else:
        roster_date = date.today()
    
    # Get all soldiers
    soldiers = Soldier.query.filter_by(status='Active').order_by(Soldier.name).all()
    
    # Get duties for the selected date
    duties = db.session.query(DutyAssignment, DutyType).join(
        DutyType, DutyAssignment.duty_type_id == DutyType.id
    ).filter(
        DutyAssignment.duty_date == roster_date
    ).all()
    
    # Create a dictionary of soldier duties
    soldier_duties = {}
    for assignment, duty_type in duties:
        if assignment.soldier_id not in soldier_duties:
            soldier_duties[assignment.soldier_id] = []
        soldier_duties[assignment.soldier_id].append({
            'duty_name': duty_type.name,
            'service_number': assignment.service_number,
            'service_shifts': assignment.get_service_shifts(),
            'shift_occurrences': assignment.get_shift_occurrences(),
            'position': assignment.position_in_team,
            'staff_count': duty_type.get_staff_count(assignment.service_number),
        })

    active_medical_cases = {
        medical_case.soldier_id: medical_case
        for medical_case in MedicalCase.query.filter(
            MedicalCase.start_date <= roster_date,
            db.or_(MedicalCase.end_date.is_(None), MedicalCase.end_date >= roster_date),
        ).order_by(MedicalCase.created_at.desc()).all()
    }
    medical_absent_count = sum(
        not medical_case.attends_roll_call
        for medical_case in active_medical_cases.values()
    )
    
    return render_template('print_roster.html', 
                         soldiers=soldiers, 
                         soldier_duties=soldier_duties,
                         medical_cases=active_medical_cases,
                         medical_absent_count=medical_absent_count,
                         roster_date=roster_date,
                         print_mode=request.args.get('print') == 'true')

@app.route('/prints/custom')
@login_required
def print_custom():
    from datetime import date
    soldiers = Soldier.query.order_by(Soldier.name).all()
    
    # Get selected fields from query parameters
    selected_fields = request.args.getlist('fields')
    
    return render_template('print_custom.html',
                         soldiers=soldiers,
                         selected_fields=selected_fields,
                         print_mode=request.args.get('print') == 'true',
                         date=date)

# Equipment Management Routes
@app.route('/equipment')
@login_required
def equipment():
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    type_filter = request.args.get('type', '')
    
    query = Equipment.query
    
    if search:
        query = query.filter(
            db.or_(
                Equipment.name.contains(search),
                Equipment.serial_number.contains(search)
            )
        )
    
    if status_filter:
        query = query.filter_by(status=status_filter)
    
    if type_filter:
        query = query.filter_by(equipment_type=type_filter)
    
    equipment_list = query.order_by(Equipment.name).all()
    
    # Get available soldiers for assignment
    available_soldiers = Soldier.query.filter_by(status='Active').order_by(Soldier.name).all()
    
    return render_template('equipment.html', 
                         equipment_list=equipment_list,
                         available_soldiers=available_soldiers,
                         search=search, 
                         status_filter=status_filter,
                         type_filter=type_filter)

@app.route('/equipment/add', methods=['POST'])
@login_required
def add_equipment():
    try:
        equipment = Equipment(
            name=request.form['name'],
            serial_number=request.form.get('serial_number'),
            equipment_type=request.form['equipment_type'],
            notes=request.form.get('notes', '')
        )
        
        db.session.add(equipment)
        db.session.commit()
        
        log_activity('add_equipment', 'equipment', equipment.id, 
                    f'Added equipment: {equipment.name}')
        
        flash(f'Εξοπλισμός {equipment.name} προστέθηκε επιτυχώς!', 'success')
        
    except Exception as e:
        flash(f'Σφάλμα κατά την προσθήκη εξοπλισμού: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('equipment'))

@app.route('/equipment/<int:equipment_id>/assign', methods=['POST'])
@login_required
def assign_equipment(equipment_id):
    equipment_item = Equipment.query.get_or_404(equipment_id)
    
    try:
        soldier_id = request.form.get('soldier_id')
        if soldier_id:
            soldier = Soldier.query.get(soldier_id)
            equipment_item.assigned_to = soldier_id
            equipment_item.assigned_date = date.today()
            equipment_item.status = 'Assigned'
            
            log_activity('assign_equipment', 'equipment', equipment_item.id, 
                        f'Assigned {equipment_item.name} to {soldier.name}')
            
            flash(f'Εξοπλισμός ανατέθηκε στον {soldier.name}', 'success')
        else:
            # Unassign equipment
            old_soldier_name = equipment_item.soldier.name if equipment_item.soldier else 'Unknown'
            equipment_item.assigned_to = None
            equipment_item.assigned_date = None
            equipment_item.status = 'Available'
            
            log_activity('unassign_equipment', 'equipment', equipment_item.id, 
                        f'Unassigned {equipment_item.name} from {old_soldier_name}')
            
            flash(f'Εξοπλισμός απελευθερώθηκε', 'success')
        
        db.session.commit()
        
    except Exception as e:
        flash(f'Σφάλμα κατά την ανάθεση: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('equipment'))

# Leave Management Routes
@app.route('/leaves')
@login_required
def leaves():
    status_filter = request.args.get('status', '')
    month_filter = request.args.get('month', '')
    
    query = SoldierLeave.query.join(Soldier)
    
    if status_filter:
        query = query.filter(SoldierLeave.status == status_filter)
    
    if month_filter:
        try:
            year, month = month_filter.split('-')
            query = query.filter(
                db.extract('year', SoldierLeave.start_date) == int(year),
                db.extract('month', SoldierLeave.start_date) == int(month)
            )
        except:
            pass
    
    leaves_list = query.order_by(SoldierLeave.start_date.desc()).all()
    
    # Get current active leaves
    active_leaves = SoldierLeave.query.filter(
        SoldierLeave.status == 'Approved',
        SoldierLeave.start_date <= date.today(),
        SoldierLeave.end_date >= date.today()
    ).all()
    
    return render_template('leaves.html', 
                         leaves_list=leaves_list,
                         active_leaves=active_leaves,
                         status_filter=status_filter,
                         month_filter=month_filter)

@app.route('/leaves/add', methods=['GET', 'POST'])
@login_required
def add_leave():
    if request.method == 'POST':
        try:
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
            days_count = (end_date - start_date).days + 1
            
            leave = SoldierLeave(
                soldier_id=int(request.form['soldier_id']),
                leave_type=request.form['leave_type'],
                start_date=start_date,
                end_date=end_date,
                days_count=days_count,
                reason=request.form.get('reason', ''),
                notes=request.form.get('notes', '')
            )
            
            db.session.add(leave)
            db.session.commit()
            
            log_activity('add_leave', 'leave', leave.id, 
                        f'Added leave for {leave.soldier.name}')
            
            flash(f'Άδεια για τον {leave.soldier.name} καταχωρήθηκε!', 'success')
            return redirect(url_for('leaves'))
            
        except Exception as e:
            flash(f'Σφάλμα κατά την προσθήκη άδειας: {str(e)}', 'error')
            db.session.rollback()
    
    soldiers = Soldier.query.filter_by(status='Active').order_by(Soldier.name).all()
    return render_template('add_leave.html', soldiers=soldiers)

@app.route('/leaves/<int:leave_id>/approve', methods=['POST'])
@login_required
def approve_leave(leave_id):
    leave = SoldierLeave.query.get_or_404(leave_id)
    
    try:
        leave.status = 'Approved'
        leave.approved_by = current_user.id
        leave.approved_date = datetime.utcnow()
        
        db.session.commit()
        
        log_activity('approve_leave', 'leave', leave.id, 
                    f'Approved leave for {leave.soldier.name}')
        
        flash(f'Άδεια εγκρίθηκε για τον {leave.soldier.name}', 'success')
        
    except Exception as e:
        flash(f'Σφάλμα κατά την έγκριση: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('leaves'))


# Medical case management
@app.route('/medical')
@login_required
def medical_cases():
    today = date.today()
    cases = MedicalCase.query.join(Soldier).order_by(
        MedicalCase.start_date.desc(), MedicalCase.created_at.desc()
    ).all()
    active_cases = [medical_case for medical_case in cases if medical_case.is_active_on(today)]
    return render_template(
        'medical_cases.html', cases=cases, active_cases=active_cases, today=today
    )


@app.route('/medical/add', methods=['GET', 'POST'])
@login_required
def add_medical_case():
    if request.method == 'POST':
        try:
            soldier = db.get_or_404(Soldier, int(request.form['soldier_id']))
            illness = request.form.get('illness', '').strip()
            location = request.form.get('location')
            start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
            end_date_value = request.form.get('end_date', '').strip()
            end_date = (
                datetime.strptime(end_date_value, '%Y-%m-%d').date()
                if end_date_value else None
            )

            if not illness:
                raise ValueError('Η ασθένεια είναι υποχρεωτική.')
            if location not in {'Battalion', 'Infirmary'}:
                raise ValueError('Μη έγκυρη τοποθεσία νοσηλείας.')
            if end_date and end_date < start_date:
                raise ValueError('Η ημερομηνία λήξης δεν μπορεί να προηγείται της έναρξης.')

            overlap_end = end_date or date.max
            overlapping_case = MedicalCase.query.filter(
                MedicalCase.soldier_id == soldier.id,
                MedicalCase.start_date <= overlap_end,
                db.or_(MedicalCase.end_date.is_(None), MedicalCase.end_date >= start_date),
            ).first()
            if overlapping_case:
                raise ValueError(
                    'Υπάρχει ήδη περιστατικό ασθένειας για τον στρατιώτη '
                    'στο επιλεγμένο διάστημα.'
                )

            attends_roll_call = (
                location == 'Battalion'
                and request.form.get('attends_roll_call') == 'yes'
            )
            medical_case = MedicalCase(
                soldier_id=soldier.id,
                illness=illness,
                location=location,
                attends_roll_call=attends_roll_call,
                start_date=start_date,
                end_date=end_date,
                notes=request.form.get('notes', '').strip(),
                created_by=current_user.id,
            )
            db.session.add(medical_case)
            db.session.commit()
            log_activity(
                'add_medical_case', 'medical_case', medical_case.id,
                f'Καταχώρηση ασθένειας για {soldier.name}: {illness}'
            )
            flash(f'Η ασθένεια του {soldier.name} καταχωρήθηκε.', 'success')
            return redirect(url_for('medical_cases'))
        except (ValueError, TypeError) as exc:
            db.session.rollback()
            flash(str(exc) or 'Ελέγξτε τα στοιχεία της καταχώρησης.', 'error')
        except Exception as exc:
            db.session.rollback()
            logging.exception('Could not create medical case')
            flash(f'Σφάλμα κατά την καταχώρηση: {exc}', 'error')

    soldiers = Soldier.query.filter_by(status='Active').order_by(Soldier.name).all()
    return render_template('add_medical_case.html', soldiers=soldiers, today=date.today())


@app.route('/medical/<int:case_id>/close', methods=['POST'])
@login_required
def close_medical_case(case_id):
    medical_case = db.get_or_404(MedicalCase, case_id)
    close_date_value = request.form.get('end_date', date.today().isoformat())
    try:
        close_date = datetime.strptime(close_date_value, '%Y-%m-%d').date()
        if close_date < medical_case.start_date:
            raise ValueError('Η ημερομηνία λήξης δεν μπορεί να προηγείται της έναρξης.')
        medical_case.end_date = close_date
        db.session.commit()
        log_activity(
            'close_medical_case', 'medical_case', medical_case.id,
            f'Λήξη ασθένειας για {medical_case.soldier.name}'
        )
        flash(f'Ολοκληρώθηκε η καταχώρηση για τον {medical_case.soldier.name}.', 'success')
    except ValueError as exc:
        db.session.rollback()
        flash(str(exc), 'error')
    return redirect(url_for('medical_cases'))

# Staffing Alerts
@app.route('/staffing_alerts')
@login_required
def staffing_alerts():
    # Get current unresolved alerts
    alerts = StaffingAlert.query.filter_by(resolved=False).order_by(
        StaffingAlert.severity.desc(), 
        StaffingAlert.created_at.desc()
    ).all()
    
    return render_template('staffing_alerts.html', alerts=alerts, date=date)

@app.route('/check_staffing/<date_str>')
@login_required
def check_staffing(date_str):
    """Check staffing levels for a specific date and create alerts if needed"""
    try:
        check_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Clear existing alerts for this date
        StaffingAlert.query.filter_by(alert_date=check_date).delete()
        
        duty_types = DutyType.query.filter_by(is_active=True).all()
        alerts_created = 0
        
        for duty_type in duty_types:
            required_staff = sum(
                duty_type.get_staff_count(service_number)
                for service_number in duty_type.get_service_numbers()
            )
            
            # Count available soldiers for this duty type
            available_soldiers = Soldier.query.filter(
                Soldier.status == 'Active',
                Soldier.exemption_no_duty == False
            ).all()
            
            # Filter out soldiers on leave
            soldiers_on_leave = SoldierLeave.query.filter(
                SoldierLeave.status == 'Approved',
                SoldierLeave.start_date <= check_date,
                SoldierLeave.end_date >= check_date
            ).all()
            
            leave_soldier_ids = [leave.soldier_id for leave in soldiers_on_leave]
            medical_soldier_ids = {
                soldier_id for (soldier_id,) in db.session.query(MedicalCase.soldier_id).filter(
                    MedicalCase.start_date <= check_date,
                    db.or_(MedicalCase.end_date.is_(None), MedicalCase.end_date >= check_date),
                ).all()
            }
            available_count = len([
                s for s in available_soldiers
                if s.id not in leave_soldier_ids and s.id not in medical_soldier_ids
            ])
            
            if available_count < required_staff:
                shortage = required_staff - available_count
                
                # Determine severity
                if shortage >= required_staff * 0.75:
                    severity = 'Critical'
                elif shortage >= required_staff * 0.5:
                    severity = 'High'
                elif shortage >= required_staff * 0.25:
                    severity = 'Medium'
                else:
                    severity = 'Low'
                
                alert = StaffingAlert(
                    alert_date=check_date,
                    duty_type_id=duty_type.id,
                    required_staff=required_staff,
                    available_staff=available_count,
                    shortage=shortage,
                    severity=severity
                )
                
                db.session.add(alert)
                alerts_created += 1
        
        db.session.commit()
        
        if alerts_created > 0:
            flash(f'Δημιουργήθηκαν {alerts_created} ειδοποιήσεις για ανεπάρκεια προσωπικού!', 'warning')
        else:
            flash('Δεν υπάρχουν προβλήματα στελέχωσης για αυτή την ημερομηνία.', 'success')
            
    except Exception as e:
        flash(f'Σφάλμα κατά τον έλεγχο στελέχωσης: {str(e)}', 'error')
        db.session.rollback()
    
    return redirect(url_for('staffing_alerts'))
