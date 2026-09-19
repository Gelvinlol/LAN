"""Permission catalogue and endpoint access rules for unit accounts."""

PERMISSION_GROUPS = (
    ("Προσωπικό", (
        ("soldiers.view", "Προβολή προσωπικού"),
        ("soldiers.manage", "Διαχείριση προσωπικού"),
    )),
    ("Υπηρεσίες", (
        ("duties.view", "Προβολή υπηρεσιών"),
        ("duties.manage", "Διαχείριση υπηρεσιών και ωραρίων"),
    )),
    ("Πρόγραμμα", (
        ("schedule.view", "Προβολή προγράμματος"),
        ("schedule.manage", "Δημιουργία, αλλαγή και οριστικοποίηση"),
    )),
    ("Εξοπλισμός", (
        ("equipment.view", "Προβολή εξοπλισμού"),
        ("equipment.manage", "Διαχείριση εξοπλισμού"),
    )),
    ("Άδειες", (
        ("leaves.view", "Προβολή αδειών"),
        ("leaves.manage", "Καταχώριση και έγκριση αδειών"),
    )),
    ("Ιατρείο", (
        ("medical.view", "Προβολή περιστατικών"),
        ("medical.manage", "Καταχώριση και ολοκλήρωση περιστατικών"),
    )),
    ("Αναφορές", (
        ("prints.view", "Εκτυπώσεις, αναφορές και φύλλο υπηρεσίας"),
        ("alerts.view", "Ειδοποιήσεις στελέχωσης"),
        ("logs.view", "Αρχείο δραστηριοτήτων"),
    )),
)

ALL_PERMISSION_KEYS = tuple(
    key
    for _group_name, permissions in PERMISSION_GROUPS
    for key, _label in permissions
)

# Permission required by each protected endpoint. The dashboard and account
# profile actions remain available to every authenticated account.
ENDPOINT_PERMISSIONS = {
    "soldiers": "soldiers.view",
    "soldier_history": "soldiers.view",
    "soldier_profile": "soldiers.view",
    "add_soldier": "soldiers.manage",
    "add_soldier_interview": "soldiers.manage",
    "edit_soldier": "soldiers.manage",
    "delete_soldier": "soldiers.manage",
    "update_soldier_ey": "soldiers.manage",
    "duties": "duties.view",
    "get_duty_type": "duties.manage",
    "toggle_duty_type": "duties.manage",
    "edit_duty_type": "duties.manage",
    "configure_duty_numbers": "duties.manage",
    "add_duty_type": "duties.manage",
    "schedule": "schedule.view",
    "edit_assignment": "schedule.manage",
    "replacement_candidates": "schedule.manage",
    "replace_assignment_emergency": "schedule.manage",
    "generate_schedule": "schedule.manage",
    "finalize_schedule": "schedule.manage",
    "clear_schedule": "schedule.manage",
    "duty_sheet": "prints.view",
    "print_duty_sheet": "prints.view",
    "prints": "prints.view",
    "print_roster": "prints.view",
    "print_custom": "prints.view",
    "fairness_report": "prints.view",
    "equipment": "equipment.view",
    "add_equipment": "equipment.manage",
    "assign_equipment": "equipment.manage",
    "leaves": "leaves.view",
    "add_leave": "leaves.manage",
    "approve_leave": "leaves.manage",
    "medical_cases": "medical.view",
    "add_medical_case": "medical.manage",
    "close_medical_case": "medical.manage",
    "staffing_alerts": "alerts.view",
    "check_staffing": "alerts.view",
    "view_logs": "logs.view",
}
