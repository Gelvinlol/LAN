import os

import pytest
from werkzeug.security import generate_password_hash

# Database configuration must be set before importing the Flask app because
# Flask-SQLAlchemy creates and caches its engine during initialization.
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite://"

from app import app, db
from datetime import date, timedelta

from models import DutyAssignment, DutySchedule, DutyType, Soldier, SoldierLeave, User
from simple_scheduler import SimpleScheduler


@pytest.fixture()
def client():
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
        db.session.add(User(
            username="tester",
            full_name="Test User",
            role="Διοικητής",
            password_hash=generate_password_hash("test-password"),
        ))
        db.session.commit()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_protected_page_redirects_to_login(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_login_and_dashboard(client):
    response = client.post(
        "/login",
        data={"username": "tester", "password": "test-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Test User" in response.get_data(as_text=True)


def test_external_next_url_is_rejected(client):
    response = client.post(
        "/login?next=https://example.com/phishing",
        data={"username": "tester", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.headers["Location"].endswith("/")


def test_inactive_user_cannot_log_in(client):
    with app.app_context():
        user = User.query.filter_by(username="tester").one()
        user.active = False
        db.session.commit()

    response = client.post(
        "/login",
        data={"username": "tester", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Λανθασμένα στοιχεία σύνδεσης" in response.get_data(as_text=True)


def test_scheduler_prioritizes_never_assigned_and_respects_availability(client):
    schedule_date = date(2026, 9, 20)
    with app.app_context():
        never_one = Soldier(
            name="Never One", military_id="TEST001",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        never_two = Soldier(
            name="Never Two", military_id="TEST002",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        experienced = Soldier(
            name="Experienced", military_id="TEST003",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        on_leave = Soldier(
            name="On Leave", military_id="TEST004",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        duty_type = DutyType(
            name="Test Duty", team_size=2, shifts_per_day=1, is_active=True
        )
        db.session.add_all([never_one, never_two, experienced, on_leave, duty_type])
        db.session.flush()

        previous_date = schedule_date - timedelta(days=60)
        db.session.add(DutySchedule(schedule_date=previous_date, is_finalized=True))
        db.session.add(DutyAssignment(
            soldier_id=experienced.id,
            duty_type_id=duty_type.id,
            duty_date=previous_date,
            shift_number=1,
            position_in_team=1,
        ))
        db.session.add(SoldierLeave(
            soldier_id=on_leave.id,
            leave_type="Κανονική",
            start_date=schedule_date,
            end_date=schedule_date,
            days_count=1,
            status="Approved",
        ))
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is True

        assignments = DutyAssignment.query.filter_by(duty_date=schedule_date).all()
        assert len(assignments) == 2  # team size × configured one shift
        assert {assignment.soldier_id for assignment in assignments} == {
            never_one.id, never_two.id
        }
        assert {assignment.shift_number for assignment in assignments} == {1}


def test_scheduler_rotates_duty_types(client):
    schedule_date = date(2026, 9, 21)
    with app.app_context():
        repeated = Soldier(
            name="Repeated Type", military_id="ROTATE001",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        rotated = Soldier(
            name="Different Type", military_id="ROTATE002",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        target_duty = DutyType(
            name="Target Duty", team_size=1, shifts_per_day=1, is_active=True
        )
        other_duty = DutyType(
            name="Other Duty", team_size=1, shifts_per_day=1, is_active=False
        )
        db.session.add_all([repeated, rotated, target_duty, other_duty])
        db.session.flush()

        previous_date = schedule_date - timedelta(days=1)
        db.session.add(DutySchedule(schedule_date=previous_date, is_finalized=True))
        db.session.add_all([
            DutyAssignment(
                soldier_id=repeated.id, duty_type_id=target_duty.id,
                duty_date=previous_date, shift_number=1, position_in_team=1
            ),
            DutyAssignment(
                soldier_id=rotated.id, duty_type_id=other_duty.id,
                duty_date=previous_date, shift_number=1, position_in_team=1
            ),
        ])
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is True
        assignment = DutyAssignment.query.filter_by(duty_date=schedule_date).one()
        assert assignment.soldier_id == rotated.id


def test_manual_assignment_records_who_changed_it(client):
    assignment_date = date(2026, 9, 22)
    with app.app_context():
        original = Soldier(
            name="Original Soldier", military_id="EDIT001",
            enlistment_date=assignment_date - timedelta(days=100), status="Active"
        )
        replacement = Soldier(
            name="Replacement Soldier", military_id="EDIT002",
            enlistment_date=assignment_date - timedelta(days=100), status="Active"
        )
        duty_type = DutyType(
            name="Editable Duty", team_size=1, shifts_per_day=1, is_active=True
        )
        db.session.add_all([original, replacement, duty_type])
        db.session.flush()
        db.session.add(DutySchedule(schedule_date=assignment_date, is_finalized=False))
        assignment = DutyAssignment(
            soldier_id=original.id, duty_type_id=duty_type.id,
            duty_date=assignment_date, shift_number=1, position_in_team=1,
            notes="Auto-assigned by scheduler"
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id
        replacement_id = replacement.id

    client.post(
        "/login",
        data={"username": "tester", "password": "test-password"},
    )
    response = client.post(
        f"/schedule/edit_assignment/{assignment_id}",
        data={"soldier_id": str(replacement_id)},
        follow_redirects=False,
    )
    assert response.status_code == 302

    with app.app_context():
        updated = db.session.get(DutyAssignment, assignment_id)
        assert updated.soldier_id == replacement_id
        assert "Test User (tester)" in updated.notes
        assert "Original Soldier → Replacement Soldier" in updated.notes


def test_scheduler_never_assigns_two_duties_on_same_day(client):
    schedule_date = date(2026, 9, 23)
    with app.app_context():
        only_soldier = Soldier(
            name="Only Available", military_id="UNIQUE001",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        duty_type = DutyType(
            name="Two Shift Duty", team_size=1, shifts_per_day=2, is_active=True
        )
        db.session.add_all([only_soldier, duty_type])
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is False
        assignments = DutyAssignment.query.filter_by(duty_date=schedule_date).all()
        assert len(assignments) == 1
        assert assignments[0].soldier_id == only_soldier.id


def test_manual_assignment_rejects_soldier_already_scheduled(client):
    assignment_date = date(2026, 9, 24)
    with app.app_context():
        first = Soldier(
            name="First Soldier", military_id="DUP001",
            enlistment_date=assignment_date - timedelta(days=100), status="Active"
        )
        already_assigned = Soldier(
            name="Already Assigned", military_id="DUP002",
            enlistment_date=assignment_date - timedelta(days=100), status="Active"
        )
        duty_one = DutyType(name="Duty One", team_size=1, shifts_per_day=1, is_active=True)
        duty_two = DutyType(name="Duty Two", team_size=1, shifts_per_day=1, is_active=True)
        db.session.add_all([first, already_assigned, duty_one, duty_two])
        db.session.flush()
        db.session.add(DutySchedule(schedule_date=assignment_date, is_finalized=False))
        editable = DutyAssignment(
            soldier_id=first.id, duty_type_id=duty_one.id,
            duty_date=assignment_date, shift_number=1, position_in_team=1
        )
        occupied = DutyAssignment(
            soldier_id=already_assigned.id, duty_type_id=duty_two.id,
            duty_date=assignment_date, shift_number=1, position_in_team=1
        )
        db.session.add_all([editable, occupied])
        db.session.commit()
        editable_id = editable.id
        first_id = first.id
        occupied_id = already_assigned.id

    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    response = client.post(
        f"/schedule/edit_assignment/{editable_id}",
        data={"soldier_id": str(occupied_id)},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "έχει ήδη τοποθετηθεί" in response.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(DutyAssignment, editable_id).soldier_id == first_id


def test_draft_duties_count_only_after_finalization(client):
    today = date.today()
    finalized_date = today - timedelta(days=2)
    draft_date = today - timedelta(days=1)

    with app.app_context():
        soldier = Soldier(
            name="Finalization Test", military_id="FINAL001",
            enlistment_date=today - timedelta(days=100), status="Active"
        )
        duty_type = DutyType(
            name="Finalization Duty", team_size=1, shifts_per_day=1, is_active=True
        )
        db.session.add_all([soldier, duty_type])
        db.session.flush()
        finalized_schedule = DutySchedule(
            schedule_date=finalized_date, is_finalized=True
        )
        draft_schedule = DutySchedule(schedule_date=draft_date, is_finalized=False)
        db.session.add_all([finalized_schedule, draft_schedule])
        db.session.add_all([
            DutyAssignment(
                soldier_id=soldier.id, duty_type_id=duty_type.id,
                duty_date=finalized_date, shift_number=1, position_in_team=1
            ),
            DutyAssignment(
                soldier_id=soldier.id, duty_type_id=duty_type.id,
                duty_date=draft_date, shift_number=1, position_in_team=1
            ),
        ])
        db.session.commit()

        assert soldier.get_total_finalized_duties() == 1
        assert soldier.get_duty_count_last_days() == 1
        assert soldier.get_duty_counts_by_type() == {"Finalization Duty": 1}
        assert len(soldier.get_duty_history()) == 1
        assert soldier.get_last_duty_date() == finalized_date

        draft_schedule.is_finalized = True
        db.session.commit()

        assert soldier.get_total_finalized_duties() == 2
        assert soldier.get_duty_count_last_days() == 2
        assert soldier.get_duty_counts_by_type() == {"Finalization Duty": 2}
        assert len(soldier.get_duty_history()) == 2
        assert soldier.get_last_duty_date() == draft_date
