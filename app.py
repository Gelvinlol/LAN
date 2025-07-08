import os
import logging
from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_login import LoginManager

# Set up logging for debugging
logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "military-unit-management-secret-key-2024")
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Configure the database
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL") or "sqlite:///military_unit.db"
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize the app with the extension
db.init_app(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Παρακαλώ συνδεθείτε για να προσπελάσετε αυτή τη σελίδα.'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

# Import routes after app creation to avoid circular imports
from routes import *

with app.app_context():
    # Import models to ensure tables are created
    import models
    db.create_all()
    
    # Initialize default users if none exist
    from models import User, DutyType, Soldier
    from werkzeug.security import generate_password_hash
    import random
    from datetime import date, timedelta
    
    # Create default users if they don't exist
    default_users = [
        {"username": "commander", "password": "commander123", "role": "Διοικητής", "full_name": "Διοικητής Μονάδας"},
        {"username": "staff", "password": "staff123", "role": "Υπασπιστήριο", "full_name": "Υπασπιστήριο"},
        {"username": "audm", "password": "audm123", "role": "ΑΥΔΜ", "full_name": "ΑΥΔΜ"},
        {"username": "archive", "password": "archive123", "role": "ΓΡΑΦΙΟ ΑΡΧΗΛΟΧΕΙΑ", "full_name": "Γραφίο Αρχηλόχεια"}
    ]
    
    for user_data in default_users:
        existing = User.query.filter_by(username=user_data["username"]).first()
        if not existing:
            user = User(
                username=user_data["username"],
                password_hash=generate_password_hash(user_data["password"]),
                role=user_data["role"],
                full_name=user_data["full_name"]
            )
            db.session.add(user)
    
    # Initialize default duty types if none exist
    default_duties = [
        {"name": "Περίπολος", "description": "Patrol duty", "team_size": 2, "shifts_per_day": 3},
        {"name": "Κεντρική Πύλη", "description": "Main Gate duty", "team_size": 2, "shifts_per_day": 3},
        {"name": "Θαλαμοφύλακας", "description": "Dorm Watch duty", "team_size": 1, "shifts_per_day": 3},
        {"name": "Μαγειρεία", "description": "Cookhouse duty", "team_size": 3, "shifts_per_day": 1},
        {"name": "Λάντζα", "description": "Dishwashing duty", "team_size": 2, "shifts_per_day": 1}
    ]
    
    for duty_data in default_duties:
        existing = DutyType.query.filter_by(name=duty_data["name"]).first()
        if not existing:
            duty_type = DutyType(**duty_data)
            db.session.add(duty_type)
    
    # Add 50 demo soldiers if none exist
    if Soldier.query.count() == 0:
        greek_first_names = [
            "Αλέξανδρος", "Δημήτριος", "Γιάννης", "Νικόλαος", "Κωνσταντίνος", "Μιχάλης", "Παναγιώτης", "Βασίλειος",
            "Αντώνιος", "Στέφανος", "Θανάσης", "Σπύρος", "Γιώργος", "Χρήστος", "Παύλος", "Ηλίας", "Μάνος", "Πέτρος",
            "Σάκης", "Βάγγος", "Κώστας", "Τάσος", "Φώτης", "Γιάνγκος", "Λάμπρος", "Νίκος", "Τάκης", "Γιάννας",
            "Άγγελος", "Μάριος", "Τόλης", "Σταύρος", "Νικολός", "Δημήτρης", "Βάσος", "Γρηγόρης", "Τάσος", "Λευτέρης",
            "Σωκράτης", "Στράτος", "Αργύρης", "Νίκος", "Άρης", "Βαγγέλης", "Φοίβος", "Στέλιος", "Μάνος", "Σάββας",
            "Ζήσης", "Κόστας"
        ]
        
        greek_last_names = [
            "Παπαδόπουλος", "Παπαγιάννης", "Κωνσταντίνου", "Γεωργίου", "Δημητρίου", "Νικολάου", "Ιωάννου", "Πετρίδης",
            "Αντωνίου", "Στεφάνου", "Μιχαηλίδης", "Βασιλείου", "Χριστοδούλου", "Παναγιώτου", "Ελευθερίου", "Σαμαράς",
            "Καραγιάννης", "Μαυρίδης", "Κοτσώνης", "Βλάχος", "Ζαχαρίου", "Αγγελίδης", "Παπανικολάου", "Σταμάτης",
            "Γιαννακόπουλος", "Μαρίνος", "Κούτσης", "Αντωνόπουλος", "Λάζαρος", "Σιδέρης", "Ταξιάρχης", "Λεβέντης",
            "Αρβανίτης", "Κανελλόπουλος", "Χατζής", "Μακρής", "Σπανός", "Λιβάνης", "Κατσίκης", "Παπαστάθης",
            "Μαστρογιάννης", "Ρούσσος", "Κολέτσος", "Θεοδώρου", "Αλεξίου", "Κυριακίδης", "Τσιόδρας", "Βάμβας",
            "Κομνηνός", "Ζούρος"
        ]
        
        specialties = [
            "Πεζικό", "Τεχνικός", "Διαβιβάσεις", "Μηχανικός", "Οδηγός", "Μάγειρας", "Κλητήρας", "Φρουρός",
            "Γραφέας", "Τυπογράφος", "Ηλεκτρολόγος", "Υδραυλικός", "Καταδρομέας", "Ελεύθερος Σκοπευτής"
        ]
        
        for i in range(50):
            first_name = random.choice(greek_first_names)
            last_name = random.choice(greek_last_names)
            full_name = f"{first_name} {last_name}"
            
            # Generate realistic military ID
            military_id = f"{random.randint(2020, 2024)}{random.randint(100000, 999999)}"
            
            # Random enlistment date within last 2 years
            enlistment_date = date.today() - timedelta(days=random.randint(30, 730))
            
            # Occasional exemptions (5% chance each)
            exemption_no_duty = random.random() < 0.05
            exemption_no_shaving = random.random() < 0.05
            exemption_no_boots = random.random() < 0.05
            
            # 90% active, 10% on leave
            status = "Active" if random.random() < 0.9 else "On Leave"
            
            soldier = Soldier(
                name=full_name,
                military_id=military_id,
                enlistment_date=enlistment_date,
                specialty=random.choice(specialties),
                status=status,
                exemption_no_duty=exemption_no_duty,
                exemption_no_shaving=exemption_no_shaving,
                exemption_no_boots=exemption_no_boots
            )
            db.session.add(soldier)
    
    db.session.commit()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
