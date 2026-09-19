import os
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

# Database configuration must be set before importing the Flask app because
# Flask-SQLAlchemy creates and caches its engine during initialization.
os.environ["APP_ENV"] = "development"
os.environ["DATABASE_URL"] = "sqlite://"

from app import app, db
from datetime import date, timedelta

from models import ActivityLog, DutyAssignment, DutyNumberRequirement, DutySchedule, DutyServiceShift, DutyType, MedicalCase, Soldier, SoldierLeave, UnitSettings, User, UserPermission
from simple_scheduler import SimpleScheduler
from operational_calendar import is_weekend_or_holiday
from reporting import build_fairness_report
from service_numbers import (
    SERVICE_NUMBER_SHIFTS,
    get_service_number_at,
    get_service_number_shifts,
    get_service_shift_occurrences,
)


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
    login_page = client.get("/login").get_data(as_text=True)
    assert "images/ges-emblem.png" in login_page
    assert "images/chronou-feidou-emblem.png" in login_page

    response = client.post(
        "/login",
        data={"username": "tester", "password": "test-password"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    dashboard = response.get_data(as_text=True)
    assert "Test User" in dashboard
    assert "images/chronou-feidou-emblem.png" in dashboard
    assert "vendor/bootstrap/css/bootstrap.min.css" in dashboard
    assert "vendor/bootstrap/js/bootstrap.bundle.min.js" in dashboard
    assert "vendor/fontawesome/css/all.min.css" in dashboard
    assert "cdn.jsdelivr.net" not in dashboard
    assert "cdnjs.cloudflare.com" not in dashboard
    assert "images/ges-emblem.png" in dashboard


def test_runtime_frontend_has_no_external_dependencies(client):
    project_root = Path(__file__).resolve().parents[1]
    runtime_files = [
        *project_root.joinpath("templates").glob("*.html"),
        *project_root.joinpath("static", "js").glob("*.js"),
        *project_root.joinpath("static", "css").glob("*.css"),
    ]
    for runtime_file in runtime_files:
        content = runtime_file.read_text(encoding="utf-8")
        assert "https://" not in content, runtime_file
        assert "http://" not in content, runtime_file

    response = client.get("/login")
    policy = response.headers["Content-Security-Policy"]
    assert "connect-src 'self'" in policy
    assert "default-src 'self'" in policy


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
            service_number=1,
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
        assert len(assignments) == 3
        assert {never_one.id, never_two.id}.issubset(
            {assignment.soldier_id for assignment in assignments}
        )
        assert {assignment.service_number for assignment in assignments} == {1, 2, 3}


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
                duty_date=previous_date, service_number=1, position_in_team=1
            ),
            DutyAssignment(
                soldier_id=rotated.id, duty_type_id=other_duty.id,
                duty_date=previous_date, service_number=1, position_in_team=1
            ),
        ])
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is False
        assignment = DutyAssignment.query.filter_by(
            duty_date=schedule_date, service_number=1
        ).one()
        assert assignment.soldier_id == rotated.id


def test_armed_duty_excludes_unarmed_and_i4_soldiers(client):
    schedule_date = date(2026, 9, 23)
    with app.app_context():
        armed = Soldier(
            name="Armed Eligible", military_id="ARMED001",
            enlistment_date=schedule_date - timedelta(days=100), status="Active",
            medical_category="Ι2",
        )
        unarmed = Soldier(
            name="Unarmed", military_id="ARMED002",
            enlistment_date=schedule_date - timedelta(days=100), status="Active",
            medical_category="Ι3 ΑΟΠΛΟ",
        )
        i4 = Soldier(
            name="Category I4", military_id="ARMED003",
            enlistment_date=schedule_date - timedelta(days=100), status="Active",
            medical_category="Ι4",
        )
        duty_type = DutyType(
            name="Armed Gate", is_active=True, requires_weapon=True
        )
        db.session.add_all([armed, unarmed, i4, duty_type])
        db.session.flush()
        db.session.add(DutyNumberRequirement(
            duty_type_id=duty_type.id, service_number=1, staff_count=1
        ))
        db.session.add(DutyServiceShift(
            duty_type_id=duty_type.id, service_number=1,
            start_time="15:00", end_time="18:00", sequence=0,
        ))
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is True
        assignment = DutyAssignment.query.filter_by(duty_date=schedule_date).one()
        assert assignment.soldier_id == armed.id


def test_special_day_fairness_prefers_fewer_weekend_and_holiday_duties(client):
    target_date = date(2026, 10, 28)
    assert is_weekend_or_holiday(target_date)
    with app.app_context():
        burdened = Soldier(
            name="Special Burdened", military_id="SPECIAL001",
            enlistment_date=target_date - timedelta(days=100), status="Active",
            medical_category="Ι1",
        )
        balanced = Soldier(
            name="Special Balanced", military_id="SPECIAL002",
            enlistment_date=target_date - timedelta(days=100), status="Active",
            medical_category="Ι1",
        )
        target_duty = DutyType(name="Holiday Duty", is_active=True)
        history_duty = DutyType(name="History Duty", is_active=False)
        db.session.add_all([burdened, balanced, target_duty, history_duty])
        db.session.flush()
        db.session.add(DutyNumberRequirement(
            duty_type_id=target_duty.id, service_number=1, staff_count=1
        ))
        db.session.add(DutyServiceShift(
            duty_type_id=target_duty.id, service_number=1,
            start_time="15:00", end_time="18:00", sequence=0,
        ))
        special_history = date(2026, 10, 25)  # Sunday
        weekday_history = date(2026, 10, 26)  # Monday
        db.session.add_all([
            DutySchedule(schedule_date=special_history, is_finalized=True),
            DutySchedule(schedule_date=weekday_history, is_finalized=True),
            DutyAssignment(
                soldier_id=burdened.id, duty_type_id=history_duty.id,
                duty_date=special_history, service_number=1,
            ),
            DutyAssignment(
                soldier_id=balanced.id, duty_type_id=history_duty.id,
                duty_date=weekday_history, service_number=1,
            ),
        ])
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(target_date) is True
        assignment = DutyAssignment.query.filter_by(duty_date=target_date).one()
        assert assignment.soldier_id == balanced.id


def test_emergency_replacement_allows_finalized_schedule_and_filters_weapon(client):
    assignment_date = date(2026, 9, 24)
    with app.app_context():
        original = Soldier(
            name="Original Armed", military_id="REPLACE001",
            enlistment_date=assignment_date - timedelta(days=100), status="Active",
            medical_category="Ι1",
        )
        eligible = Soldier(
            name="Eligible Armed", military_id="REPLACE002",
            enlistment_date=assignment_date - timedelta(days=100), status="Active",
            medical_category="Ι3 ΕΝΟΠΛΟ",
        )
        unarmed = Soldier(
            name="Ineligible Unarmed", military_id="REPLACE003",
            enlistment_date=assignment_date - timedelta(days=100), status="Active",
            medical_category="Ι3 ΑΟΠΛΟ",
        )
        duty_type = DutyType(
            name="Finalized Armed Patrol", is_active=False, requires_weapon=True
        )
        db.session.add_all([original, eligible, unarmed, duty_type])
        db.session.flush()
        db.session.add(DutySchedule(
            schedule_date=assignment_date, is_finalized=True
        ))
        assignment = DutyAssignment(
            soldier_id=original.id, duty_type_id=duty_type.id,
            duty_date=assignment_date, service_number=1,
        )
        db.session.add(assignment)
        db.session.commit()
        assignment_id = assignment.id
        eligible_id = eligible.id

    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    page = client.get(f"/schedule/assignment/{assignment_id}/replacement")
    text = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Eligible Armed" in text
    assert "Ineligible Unarmed" not in text

    response = client.post(
        f"/schedule/assignment/{assignment_id}/replace",
        data={"soldier_id": str(eligible_id), "reason": "Έκτακτη ασθένεια"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        assignment = db.session.get(DutyAssignment, assignment_id)
        assert assignment.soldier_id == eligible_id
        assert "Έκτακτη ασθένεια" in assignment.notes


def test_fairness_report_uses_only_finalized_duties(client):
    special_date = date(2026, 9, 20)  # Sunday
    weekday_date = date(2026, 9, 21)
    draft_date = date(2026, 9, 22)
    with app.app_context():
        soldier = Soldier(
            name="Report Soldier", military_id="REPORT001",
            enlistment_date=special_date - timedelta(days=100), status="Active",
            medical_category="Ι1",
        )
        duty_type = DutyType(name="Report Gate", is_active=False)
        db.session.add_all([soldier, duty_type])
        db.session.flush()
        db.session.add_all([
            DutySchedule(schedule_date=special_date, is_finalized=True),
            DutySchedule(schedule_date=weekday_date, is_finalized=True),
            DutySchedule(schedule_date=draft_date, is_finalized=False),
            DutyAssignment(
                soldier_id=soldier.id, duty_type_id=duty_type.id,
                duty_date=special_date, service_number=1,
            ),
            DutyAssignment(
                soldier_id=soldier.id, duty_type_id=duty_type.id,
                duty_date=weekday_date, service_number=1,
            ),
            DutyAssignment(
                soldier_id=soldier.id, duty_type_id=duty_type.id,
                duty_date=draft_date, service_number=1,
            ),
        ])
        db.session.commit()

        report = build_fairness_report(special_date, draft_date)
        assert report["total_assignments"] == 2
        assert report["total_night"] == 2
        assert report["total_special"] == 1
        assert report["rows"][0]["total"] == 2
        assert report["rows"][0]["average_rest_hours"] == 6.0

    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    response = client.get(
        "/reports/fairness?start_date=2026-09-20&end_date=2026-09-22"
    )
    assert response.status_code == 200
    assert "Report Soldier" in response.get_data(as_text=True)


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
            duty_date=assignment_date, service_number=1, position_in_team=1,
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
            duty_date=assignment_date, service_number=1, position_in_team=1
        )
        occupied = DutyAssignment(
            soldier_id=already_assigned.id, duty_type_id=duty_two.id,
            duty_date=assignment_date, service_number=1, position_in_team=1
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
                duty_date=finalized_date, service_number=1, position_in_team=1
            ),
            DutyAssignment(
                soldier_id=soldier.id, duty_type_id=duty_type.id,
                duty_date=draft_date, service_number=1, position_in_team=1
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


def test_infirmary_case_is_out_of_roll_call_and_printed(client):
    today = date.today()
    with app.app_context():
        soldier = Soldier(
            name="Medical Test", military_id="MED001",
            enlistment_date=today - timedelta(days=100), status="Active"
        )
        db.session.add(soldier)
        db.session.commit()
        soldier_id = soldier.id

    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    response = client.post(
        "/medical/add",
        data={
            "soldier_id": str(soldier_id),
            "illness": "Γρίπη",
            "location": "Infirmary",
            "attends_roll_call": "yes",
            "start_date": today.isoformat(),
            "end_date": "",
            "notes": "Παρακολούθηση",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        medical_case = MedicalCase.query.one()
        assert medical_case.attends_roll_call is False
        assert medical_case.report_status == "Δεν συμμετέχει — Ιατρείο"

    report = client.get(f"/prints/roster?date={today.isoformat()}")
    report_text = report.get_data(as_text=True)
    assert "Εκτός Αναφοράς" in report_text
    assert "Γρίπη" in report_text
    assert "Ιατρείο" in report_text


def test_medical_case_excludes_soldier_from_scheduler(client):
    schedule_date = date(2026, 9, 25)
    with app.app_context():
        sick = Soldier(
            name="Sick Soldier", military_id="MED002",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        healthy = Soldier(
            name="Healthy Soldier", military_id="MED003",
            enlistment_date=schedule_date - timedelta(days=100), status="Active"
        )
        duty_type = DutyType(
            name="Medical Availability Duty", team_size=1,
            shifts_per_day=1, is_active=True
        )
        db.session.add_all([sick, healthy, duty_type])
        db.session.flush()
        db.session.add(MedicalCase(
            soldier_id=sick.id,
            illness="Τραυματισμός",
            location="Battalion",
            attends_roll_call=True,
            start_date=schedule_date,
        ))
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is False
        assignments = DutyAssignment.query.filter_by(duty_date=schedule_date).all()
        assert {assignment.soldier_id for assignment in assignments} == {healthy.id}


@pytest.mark.parametrize(
    ("service_number", "expected"),
    [
        (1, [("15:00", "18:00"), ("00:00", "02:00"), ("06:00", "09:00")]),
        (2, [("18:00", "21:00"), ("02:00", "04:00"), ("09:00", "12:00")]),
        (3, [("21:00", "00:00"), ("04:00", "06:00"), ("12:00", "15:00")]),
    ],
)
def test_service_number_has_three_canonical_shifts(service_number, expected):
    shifts = get_service_number_shifts(service_number)
    assert [(shift.start, shift.end) for shift in shifts] == expected
    assert SERVICE_NUMBER_SHIFTS[service_number] == shifts


@pytest.mark.parametrize(
    ("clock_time", "expected_number"),
    [
        ("01:00", 1), ("03:00", 2), ("05:00", 3),
        ("08:00", 1), ("10:00", 2), ("14:00", 3),
        ("16:00", 1), ("19:00", 2), ("22:00", 3),
    ],
)
def test_service_number_lookup_by_time(clock_time, expected_number):
    assert get_service_number_at(clock_time) == expected_number


def test_service_number_occurrences_cross_midnight_on_operational_day():
    operational_date = date(2026, 9, 16)
    occurrences = get_service_shift_occurrences(operational_date, 3)
    assert occurrences[0][0].isoformat() == "2026-09-16T21:00:00"
    assert occurrences[0][1].isoformat() == "2026-09-17T00:00:00"
    assert occurrences[1][0].isoformat() == "2026-09-17T04:00:00"
    assert occurrences[2][1].isoformat() == "2026-09-17T15:00:00"


def test_service_number_pages_render_all_inherited_shifts(client):
    schedule_date = date(2026, 9, 26)
    with app.app_context():
        soldiers = [
            Soldier(
                name=f"Number {number}", military_id=f"NUM00{number}",
                enlistment_date=schedule_date - timedelta(days=100), status="Active"
            )
            for number in (1, 2, 3)
        ]
        duty_type = DutyType(
            name="Gate A", team_size=1, shifts_per_day=3, is_active=True
        )
        db.session.add_all([*soldiers, duty_type])
        db.session.flush()
        db.session.add(DutySchedule(schedule_date=schedule_date, is_finalized=True))
        for service_number, soldier in enumerate(soldiers, 1):
            db.session.add(DutyAssignment(
                soldier_id=soldier.id,
                duty_type_id=duty_type.id,
                duty_date=schedule_date,
                service_number=service_number,
            ))
        db.session.commit()
        first_soldier_id = soldiers[0].id

    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    urls = [
        f"/schedule?date={schedule_date.isoformat()}",
        f"/duty_sheet?date={schedule_date.isoformat()}",
        f"/prints/roster?date={schedule_date.isoformat()}",
        f"/soldiers/{first_soldier_id}/history",
    ]
    pages = [client.get(url) for url in urls]
    assert all(page.status_code == 200 for page in pages)
    combined = "\n".join(page.get_data(as_text=True) for page in pages)
    assert "Νο 1" in combined
    assert "15:00" in combined and "00:00" in combined and "06:00" in combined
    assert "Νο 2" in combined and "18:00" in combined and "02:00" in combined
    assert "Νο 3" in combined and "21:00" in combined and "04:00" in combined


def test_commander_can_update_singleton_unit_settings(client):
    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    response = client.post(
        "/unit-settings",
        data={
            "camp_name": "Στρατόπεδο Δοκιμής",
            "unit_name": "101 Μονάδα",
            "battalion_name": "1ο Τάγμα",
            "branch": "Πεζικό",
            "formation_name": "10η Ταξιαρχία",
            "unit_code": "UNIT-101",
            "location": "Αθήνα",
            "commander_rank": "Αντισυνταγματάρχης",
            "commander_name": "Δοκιμαστικός Διοικητής",
            "contact_phone": "2100000000",
            "contact_email": "unit@example.test",
            "motto": "Χρόνου Φείδου",
            "notes": "Εσωτερική πληροφορία",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Τα στοιχεία της μονάδας αποθηκεύτηκαν" in response.get_data(as_text=True)

    with app.app_context():
        settings = db.session.get(UnitSettings, 1)
        assert settings.camp_name == "Στρατόπεδο Δοκιμής"
        assert settings.branch == "Πεζικό"
        assert settings.updated_by == User.query.filter_by(username="tester").one().id
        assert ActivityLog.query.filter_by(action="update_unit_settings").count() == 1

    dashboard = client.get("/").get_data(as_text=True)
    assert "UNIT-101" in dashboard
    assert "101 Μονάδα" in dashboard


def test_non_commander_cannot_access_unit_settings(client):
    with app.app_context():
        db.session.add(User(
            username="clerk",
            full_name="Test Clerk",
            role="Υπασπιστήριο",
            password_hash=generate_password_hash("clerk-password"),
        ))
        db.session.commit()

    login_response = client.post(
        "/login",
        data={"username": "clerk", "password": "clerk-password"},
        follow_redirects=True,
    )
    assert "Στοιχεία Μονάδας" not in login_response.get_data(as_text=True)

    response = client.get("/unit-settings", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_commander_manages_accounts_and_module_permissions(client):
    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    response = client.post(
        "/accounts/new",
        data={
            "username": "company-office",
            "full_name": "Γραφείο Αρχιλοχία",
            "role": "Γραφείο Αρχιλοχία",
            "password": "secure-password",
            "permissions": ["soldiers.view"],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "company-office" in response.get_data(as_text=True)

    with app.app_context():
        account = User.query.filter_by(username="company-office").one()
        account_id = account.id
        assert account.has_permission("soldiers.view")
        assert not account.has_permission("duties.view")
        assert {permission.permission_key for permission in account.permissions} == {
            "soldiers.view"
        }

    client.get("/logout")
    client.post(
        "/login",
        data={"username": "company-office", "password": "secure-password"},
    )
    assert client.get("/soldiers").status_code == 200
    denied = client.get("/duties", follow_redirects=False)
    assert denied.status_code == 302
    assert denied.headers["Location"].endswith("/")
    assert client.get("/accounts", follow_redirects=False).status_code == 302

    client.get("/logout")
    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    client.post(
        f"/accounts/{account_id}/edit",
        data={
            "username": "company-office",
            "full_name": "Γραφείο Αρχιλοχία",
            "role": "Γραφείο Αρχιλοχία",
            "active": "yes",
            "permissions": ["duties.manage"],
        },
        follow_redirects=True,
    )
    with app.app_context():
        account = db.session.get(User, account_id)
        assert account.active is True
        assert account.has_permission("duties.view")
        assert account.has_permission("duties.manage")
        assert not account.has_permission("soldiers.view")
        assert UserPermission.query.filter_by(user_id=account_id).count() == 1


def test_commander_cannot_deactivate_own_account(client):
    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    with app.app_context():
        commander_id = User.query.filter_by(username="tester").one().id

    response = client.post(
        f"/accounts/{commander_id}/edit",
        data={
            "username": "tester",
            "full_name": "Test User",
            "role": "Υπασπιστήριο",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        commander = db.session.get(User, commander_id)
        assert commander.active is True
        assert commander.is_commander()


def test_custom_duty_numbers_drive_scheduler_and_preserve_snapshot(client):
    schedule_date = date(2026, 9, 27)
    with app.app_context():
        soldiers = [
            Soldier(
                name=f"Custom {number}", military_id=f"CUSTOM{number}",
                enlistment_date=schedule_date - timedelta(days=100), status="Active"
            )
            for number in (1, 2, 3)
        ]
        duty_type = DutyType(
            name="Custom Hours", team_size=1, shifts_per_day=2, is_active=True
        )
        db.session.add_all([*soldiers, duty_type])
        db.session.flush()
        db.session.add_all([
            DutyNumberRequirement(
                duty_type_id=duty_type.id, service_number=1, staff_count=1,
            ),
            DutyNumberRequirement(
                duty_type_id=duty_type.id, service_number=4, staff_count=2,
            ),
            DutyServiceShift(
                duty_type_id=duty_type.id, service_number=1,
                start_time="16:00", end_time="20:00", sequence=0,
            ),
            DutyServiceShift(
                duty_type_id=duty_type.id, service_number=1,
                start_time="01:00", end_time="05:00", sequence=1,
            ),
            DutyServiceShift(
                duty_type_id=duty_type.id, service_number=4,
                start_time="20:00", end_time="00:00", sequence=0,
            ),
        ])
        db.session.commit()

        assert SimpleScheduler().generate_daily_schedule(schedule_date) is True
        assignments = DutyAssignment.query.filter_by(duty_date=schedule_date).all()
        assert len(assignments) == 3
        assert {assignment.service_number for assignment in assignments} == {1, 4}
        number_four = [
            assignment for assignment in assignments
            if assignment.service_number == 4
        ]
        assert {assignment.position_in_team for assignment in number_four} == {1, 2}
        assert len({assignment.soldier_id for assignment in assignments}) == 3
        number_one = next(
            assignment for assignment in assignments if assignment.service_number == 1
        )
        assert [(shift.start, shift.end) for shift in number_one.get_service_shifts()] == [
            ("16:00", "20:00"), ("01:00", "05:00")
        ]

        # Changing the service configuration must not rewrite historical hours.
        first_configured_shift = DutyServiceShift.query.filter_by(
            duty_type_id=duty_type.id, service_number=1, sequence=0
        ).one()
        first_configured_shift.start_time = "17:00"
        db.session.commit()
        assert [(shift.start, shift.end) for shift in number_one.get_service_shifts()] == [
            ("16:00", "20:00"), ("01:00", "05:00")
        ]


def test_duty_number_configuration_route(client):
    with app.app_context():
        duty_type = DutyType(name="Configurable Route", is_active=True)
        db.session.add(duty_type)
        db.session.commit()
        duty_id = duty_type.id

    client.post(
        "/login", data={"username": "tester", "password": "test-password"}
    )
    response = client.post(
        f"/duties/{duty_id}/numbers",
        data={
            "service_number": ["1", "4"],
            "number_1_staff_count": "1",
            "number_1_start": ["17:00", "01:00"],
            "number_1_end": ["21:00", "05:00"],
            "number_4_staff_count": "2",
            "number_4_start": ["21:00"],
            "number_4_end": ["01:00"],
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "Τα ωράρια της υπηρεσίας" in response.get_data(as_text=True)

    with app.app_context():
        configured = DutyServiceShift.query.filter_by(duty_type_id=duty_id).all()
        assert {shift.service_number for shift in configured} == {1, 4}
        assert len(configured) == 3
        requirements = DutyNumberRequirement.query.filter_by(
            duty_type_id=duty_id
        ).all()
        assert {
            requirement.service_number: requirement.staff_count
            for requirement in requirements
        } == {1: 1, 4: 2}
