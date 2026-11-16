from functools import wraps
from datetime import datetime

import math
import random

from flask import (
    Flask,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import db

app = Flask(__name__)
app.secret_key = "dev-secret-key-change-in-production"
app.teardown_appcontext(db.close_db)

db.init_db()


# =========================================
#  HELPERS
# =========================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session or session.get("role") != role:
                flash("Please login with the correct account.", "warning")
                return redirect(url_for("login"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


parent_required = role_required("parent")
teacher_required = role_required("teacher")
school_required = role_required("school")
admin_required = role_required("admin")


def current_parent():
    if session.get("role") != "parent":
        return None
    return db.get_db().execute(
        "SELECT * FROM parent WHERE id = ?", (session["user_id"],)
    ).fetchone()


def current_teacher():
    if session.get("role") != "teacher":
        return None
    return db.get_db().execute(
        "SELECT * FROM teacher WHERE id = ?", (session["user_id"],)
    ).fetchone()


def current_school():
    if session.get("role") != "school":
        return None
    return db.get_db().execute(
        "SELECT * FROM school WHERE id = ?", (session["user_id"],)
    ).fetchone()


def current_admin():
    if session.get("role") != "admin":
        return None
    return db.get_db().execute(
        "SELECT * FROM admin WHERE id = ?", (session["user_id"],)
    ).fetchone()


def current_child(parent_id):
    return db.get_db().execute(
        "SELECT * FROM child WHERE parent_id = ? ORDER BY id DESC LIMIT 1",
        (parent_id,),
    ).fetchone()


def latest_assessment(child_id):
    return db.get_db().execute(
        "SELECT * FROM assessment WHERE child_id = ? "
        "ORDER BY id DESC LIMIT 1",
        (child_id,),
    ).fetchone()


def get_or_create_certificate(child_id, assessment_id):
    connection = db.get_db()
    existing = connection.execute(
        "SELECT * FROM certificate WHERE child_id = ? AND assessment_id = ?",
        (child_id, assessment_id),
    ).fetchone()
    if existing is not None:
        return existing

    code = f"EM-{datetime.now().year}-{child_id:04d}{assessment_id:04d}"
    cursor = connection.execute(
        "INSERT OR IGNORE INTO certificate "
        "(child_id, assessment_id, certificate_code, issued_at) "
        "VALUES (?, ?, ?, ?)",
        (
            child_id,
            assessment_id,
            code,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    connection.commit()
    if cursor.rowcount == 0:
        return connection.execute(
            "SELECT * FROM certificate WHERE child_id = ? AND assessment_id = ?",
            (child_id, assessment_id),
        ).fetchone()
    return connection.execute(
        "SELECT * FROM certificate WHERE id = ?", (cursor.lastrowid,)
    ).fetchone()


def certificate_ready(child_id):
    assessment = latest_assessment(child_id)
    if assessment is None or assessment["status"] != "completed":
        return None
    return assessment


def child_readiness(connection, child_id):
    latest = connection.execute(
        "SELECT status, overall_score FROM assessment "
        "WHERE child_id = ? ORDER BY id DESC LIMIT 1",
        (child_id,),
    ).fetchone()
    assessment_pct = 0
    if latest is not None and latest["status"] == "completed":
        assessment_pct = latest["overall_score"] or 0

    obs_row = connection.execute(
        "SELECT AVG(rating) AS avg_rating FROM teacher_observation "
        "WHERE child_id = ?",
        (child_id,),
    ).fetchone()
    obs_rating = obs_row["avg_rating"] if obs_row and obs_row["avg_rating"] else 0
    obs_pct = (obs_rating / 5) * 100 if obs_rating else 0

    if assessment_pct and obs_pct:
        return round(assessment_pct * 0.75 + obs_pct * 0.25)
    return max(assessment_pct, obs_pct)


def generate_recommendations(child_id):
    connection = db.get_db()
    child = connection.execute(
        "SELECT * FROM child WHERE id = ?", (child_id,)
    ).fetchone()
    if child is None:
        return

    readiness = child_readiness(connection, child_id)

    connection.execute(
        "DELETE FROM recommendation WHERE child_id = ?", (child_id,)
    )

    schools = connection.execute("SELECT * FROM school").fetchall()
    child_loc = (child["location"] or "").lower()
    child_class = (child["current_class"] or "").lower()

    matches = []
    for school in schools:
        score = 0

        if school["location"].lower() not in child_loc:
            continue

        score += 45

        syllabus = (school["syllabus"] or "").lower()
        if "cbse" in syllabus:
            score += 20
        elif "icse" in syllabus:
            score += 18
        elif "state" in syllabus:
            score += 15

        if child_class in (school["classes"] or "").lower():
            score += 15

        score += (school["rating"] or 0) * 5
        score += readiness * 0.2

        score = min(100, round(score))
        matches.append((child_id, school["id"], score))

    connection.executemany(
        "INSERT INTO recommendation (child_id, school_id, match_score) "
        "VALUES (?, ?, ?)",
        matches,
    )


def parent_stats(parent_id):
    child = current_child(parent_id)
    stats = {
        "has_child": child is not None,
        "child_name": child["child_name"] if child else None,
        "assessment_status": "Not Started",
        "result_status": "Pending",
        "recommendation_count": 0,
        "child_id": child["id"] if child else None,
    }
    if child is not None:
        assessment = latest_assessment(child["id"])
        if assessment is not None:
            stats["assessment_status"] = (
                "Completed" if assessment["status"] == "completed" else "In Progress"
            )
            stats["result_status"] = "Ready" if assessment["status"] == "completed" else "Pending"
        stats["recommendation_count"] = db.get_db().execute(
            "SELECT COUNT(*) AS n FROM recommendation WHERE child_id = ?",
            (child["id"],),
        ).fetchone()["n"]
    return stats


SKILLS = [
    ("Language", "🔤"),
    ("Numbers", "🔢"),
    ("Colors & Shapes", "🎨"),
    ("Memory", "🧠"),
    ("Logical Thinking", "🧩"),
    ("Listening", "👂"),
    ("Communication", "💬"),
    ("Problem Solving", "💡"),
]


QUIZ_QUESTIONS = [
    # id, skill, level (1 = simple for small children, 2 = harder), question, options, answer

    # ---------------- LANGUAGE (5) ----------------
    {"id": 1, "skill": "Language", "level": 1, "icon": "📖",
     "question": "Which word starts with the letter B?",
     "options": ["Ball", "Apple", "Orange", "Egg"], "answer": 0},
    {"id": 2, "skill": "Language", "level": 1, "icon": "📖",
     "question": "Which one is an animal?",
     "options": ["Chair", "Dog", "Book", "Table"], "answer": 1},
    {"id": 3, "skill": "Language", "level": 1, "icon": "📖",
     "question": "Which picture word says CAT?",
     "options": ["Cat", "Mat", "Sun", "Car"], "answer": 0},
    {"id": 4, "skill": "Language", "level": 2, "icon": "📖",
     "question": "Which word rhymes with 'cat'?",
     "options": ["Hat", "Sun", "Tree", "Door"], "answer": 0},
    {"id": 5, "skill": "Language", "level": 2, "icon": "📖",
     "question": "Which word is the opposite of 'big'?",
     "options": ["Tall", "Small", "Wide", "Long"], "answer": 1},

    # ---------------- NUMBERS (5) ----------------
    {"id": 6, "skill": "Numbers", "level": 1, "icon": "🔢",
     "question": "What number comes after 4?",
     "options": ["3", "5", "6", "2"], "answer": 1},
    {"id": 7, "skill": "Numbers", "level": 1, "icon": "🔢",
     "question": "How many apples are there? 🍎 🍎 🍎",
     "options": ["2", "3", "4", "5"], "answer": 1},
    {"id": 8, "skill": "Numbers", "level": 1, "icon": "🔢",
     "question": "Count the fingers on one hand. How many?",
     "options": ["3", "5", "7", "10"], "answer": 1},
    {"id": 9, "skill": "Numbers", "level": 2, "icon": "🔢",
     "question": "What is 3 + 2?",
     "options": ["4", "5", "6", "7"], "answer": 1},
    {"id": 10, "skill": "Numbers", "level": 2, "icon": "🔢",
     "question": "Which number is the biggest?",
     "options": ["7", "3", "9", "5"], "answer": 2},

    # ---------------- COLORS & SHAPES (5) ----------------
    {"id": 11, "skill": "Colors & Shapes", "level": 1, "icon": "🎨",
     "question": "Which shape has three sides?",
     "options": ["Circle", "Square", "Triangle", "Rectangle"], "answer": 2},
    {"id": 12, "skill": "Colors & Shapes", "level": 1, "icon": "🎨",
     "question": "What color is the sky usually?",
     "options": ["Blue", "Green", "Black", "Pink"], "answer": 0},
    {"id": 13, "skill": "Colors & Shapes", "level": 1, "icon": "🎨",
     "question": "Which shape is round like a ball?",
     "options": ["Square", "Star", "Circle", "Triangle"], "answer": 2},
    {"id": 14, "skill": "Colors & Shapes", "level": 2, "icon": "🎨",
     "question": "What color do you get when you mix red and blue?",
     "options": ["Green", "Purple", "Orange", "Yellow"], "answer": 1},
    {"id": 15, "skill": "Colors & Shapes", "level": 2, "icon": "🎨",
     "question": "How many sides does a square have?",
     "options": ["3", "4", "5", "6"], "answer": 1},

    # ---------------- MEMORY (5) ----------------
    {"id": 16, "skill": "Memory", "level": 1, "icon": "🧠",
     "question": "Remember these numbers: 2, 5, 8. Which number was in the middle?",
     "options": ["2", "5", "8", "9"], "answer": 1},
    {"id": 17, "skill": "Memory", "level": 1, "icon": "🧠",
     "question": "Which animal did you see in this group? 🐶 🐱 🐭",
     "options": ["Dog", "Cow", "Horse", "Lion"], "answer": 0},
    {"id": 18, "skill": "Memory", "level": 1, "icon": "🧠",
     "question": "I said the word 'Mango' at the start. Which word was it?",
     "options": ["Apple", "Mango", "Banana", "Orange"], "answer": 1},
    {"id": 19, "skill": "Memory", "level": 2, "icon": "🧠",
     "question": "Remember: Red, Blue, Yellow. What was the second color?",
     "options": ["Red", "Blue", "Yellow", "Green"], "answer": 1},
    {"id": 20, "skill": "Memory", "level": 2, "icon": "🧠",
     "question": "See the cards: 7, 3, 9, 6. Which number came third?",
     "options": ["7", "3", "9", "6"], "answer": 2},

    # ---------------- LOGICAL THINKING (5) ----------------
    {"id": 21, "skill": "Logical Thinking", "level": 1, "icon": "🧩",
     "question": "Which one does not belong: Apple, Banana, Mango, Car?",
     "options": ["Apple", "Banana", "Mango", "Car"], "answer": 3},
    {"id": 22, "skill": "Logical Thinking", "level": 1, "icon": "🧩",
     "question": "Complete the pattern: 2, 4, 6, ___",
     "options": ["7", "8", "9", "10"], "answer": 1},
    {"id": 23, "skill": "Logical Thinking", "level": 1, "icon": "🧩",
     "question": "It is raining. Which one is best to use?",
     "options": ["Umbrella", "Spoon", "Bag", "Ball"], "answer": 0},
    {"id": 24, "skill": "Logical Thinking", "level": 2, "icon": "🧩",
     "question": "Day is to night, as sun is to ___",
     "options": ["Moon", "Star", "Tree", "Water"], "answer": 0},
    {"id": 25, "skill": "Logical Thinking", "level": 2, "icon": "🧩",
     "question": "What comes next? ▲ ■ ● ▲ ■ ___",
     "options": ["▲", "■", "●", "△"], "answer": 1},

    # ---------------- LISTENING (5) ----------------
    {"id": 26, "skill": "Listening", "level": 1, "icon": "👂",
     "question": "If someone says 'please pick up the red ball', what should you pick up?",
     "options": ["Blue ball", "Red ball", "Book", "Pencil"], "answer": 1},
    {"id": 27, "skill": "Listening", "level": 1, "icon": "👂",
     "question": "Listen carefully: 'Touch your nose and then clap.' What should you do first?",
     "options": ["Clap", "Jump", "Touch your nose", "Sit down"], "answer": 2},
    {"id": 28, "skill": "Listening", "level": 1, "icon": "👂",
     "question": "Your teacher says 'stand up'. What do you do?",
     "options": ["Sit down", "Stand up", "Sleep", "Run"], "answer": 1},
    {"id": 29, "skill": "Listening", "level": 2, "icon": "👂",
     "question": "Teacher says: 'clap your hands and then stamp your feet.' What do you do first?",
     "options": ["Stamp feet", "Clap hands", "Jump", "Turn around"], "answer": 1},
    {"id": 30, "skill": "Listening", "level": 2, "icon": "👂",
     "question": "Your friend asks you to pass the red crayon. Which one do you pass?",
     "options": ["Blue crayon", "Green crayon", "Red crayon", "Black crayon"], "answer": 2},

    # ---------------- COMMUNICATION (5) ----------------
    {"id": 31, "skill": "Communication", "level": 1, "icon": "💬",
     "question": "What would you say when you meet your teacher in the morning?",
     "options": ["Good morning", "Good night", "Goodbye", "Thank you"], "answer": 0},
    {"id": 32, "skill": "Communication", "level": 1, "icon": "💬",
     "question": "What should you say when someone gives you something?",
     "options": ["Sorry", "Hello", "Thank you", "Goodbye"], "answer": 2},
    {"id": 33, "skill": "Communication", "level": 1, "icon": "💬",
     "question": "When you want a glass of water, what should you say?",
     "options": ["I want water, please", "Go away", "I don't want", "Stop it"], "answer": 0},
    {"id": 34, "skill": "Communication", "level": 2, "icon": "💬",
     "question": "Your friend is crying. What should you say?",
     "options": ["Why are you crying? Can I help?", "Stop crying", "Go away", "Laugh loudly"], "answer": 0},
    {"id": 35, "skill": "Communication", "level": 2, "icon": "💬",
     "question": "If you make a mistake, what should you say?",
     "options": ["Thank you", "Sorry", "Goodbye", "Hello"], "answer": 1},

    # ---------------- PROBLEM SOLVING (5) ----------------
    {"id": 36, "skill": "Problem Solving", "level": 1, "icon": "💡",
     "question": "You are thirsty. What should you do?",
     "options": ["Drink water", "Sleep", "Run outside", "Read a book"], "answer": 0},
    {"id": 37, "skill": "Problem Solving", "level": 1, "icon": "💡",
     "question": "Your toy is under the table. What can you do?",
     "options": ["Look under the table", "Close your eyes", "Go to sleep", "Throw another toy"], "answer": 0},
    {"id": 38, "skill": "Problem Solving", "level": 1, "icon": "💡",
     "question": "It is sunny and hot. What should you wear?",
     "options": ["Heavy coat", "Hat and light clothes", "Rain boots", "Woolen scarf"], "answer": 1},
    {"id": 39, "skill": "Problem Solving", "level": 2, "icon": "💡",
     "question": "The puzzle piece does not fit here. What should you do?",
     "options": ["Force it in", "Try another place", "Throw the puzzle", "Cry"], "answer": 1},
    {"id": 40, "skill": "Problem Solving", "level": 2, "icon": "💡",
     "question": "Your pencil is broken. What is the best thing to do?",
     "options": ["Use a new sharp pencil", "Draw with your hand", "Stop working", "Break the other pencil"], "answer": 0},
]


def questions_per_skill():
    counts = {}
    for question in QUIZ_QUESTIONS:
        counts[question["skill"]] = counts.get(question["skill"], 0) + 1
    return counts


def select_questions_for_child(child):
    """Pick questions for a specific child so different children get
    different questions. Small children (Nursery/LKG) get simple level-1
    questions only; UKG and Primary children get a larger mixed set."""
    cls = (child["current_class"] or "").strip().lower()
    per_skill = 5
    if cls in ("nursery", "lkg"):
        per_skill = 3
    elif cls == "ukg":
        per_skill = 4

    selected = []
    for skill_name, _icon in SKILLS:
        bank = [q for q in QUIZ_QUESTIONS if q["skill"] == skill_name]
        if per_skill <= 3:
            pool = [q for q in bank if q["level"] == 1]
        else:
            pool = list(bank)
        random.shuffle(pool)
        selected.extend(pool[:per_skill])
    random.shuffle(selected)
    return selected


# =========================================
#  PUBLIC PAGES
# =========================================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "").strip()

        connection = db.get_db()
        user = None

        identifier = identifier.lower()

        if role == "parent":
            user = connection.execute(
                "SELECT * FROM parent WHERE LOWER(email) = ? OR LOWER(username) = ?",
                (identifier, identifier),
            ).fetchone()
            dashboard = "parent_dashboard"
            name_key = "name"
        elif role == "teacher":
            user = connection.execute(
                "SELECT * FROM teacher WHERE LOWER(email) = ? OR LOWER(username) = ?",
                (identifier, identifier),
            ).fetchone()
            dashboard = "teacher_dashboard"
            name_key = "name"
        elif role == "school":
            user = connection.execute(
                "SELECT * FROM school WHERE LOWER(username) = ? OR LOWER(email) = ?",
                (identifier, identifier),
            ).fetchone()
            dashboard = "school_dashboard"
            name_key = "name"
        elif role == "admin":
            user = connection.execute(
                "SELECT * FROM admin WHERE LOWER(username) = ? OR LOWER(email) = ?",
                (identifier, identifier),
            ).fetchone()
            dashboard = "admin_dashboard"
            name_key = "name"
        else:
            flash("Please select a role.", "warning")
            return render_template("login.html")

        if user is None or not check_password_hash(
            user["password_hash"], password
        ):
            if role == "school":
                flash(
                    "Invalid username or password. Your login username is "
                    "shown in the Admin > Schools list (e.g. "
                    "sunriseinternationalschool_1), not the school name. "
                    "Forgot your password? Ask the admin to reset it.",
                    "danger",
                )
            else:
                flash("Invalid email/username or password.", "danger")
            return render_template("login.html")

        session.clear()
        session["role"] = role
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user[name_key]}!", "success")
        return redirect(url_for(dashboard))

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    form = None
    role = "parent"

    if request.method == "POST":
        role = request.form.get("role", "parent").strip()
        form = {
            "full_name": request.form.get("full_name", "").strip(),
            "username": request.form.get("username", "").strip().lower(),
            "email": request.form.get("email", "").strip().lower(),
            "phone": request.form.get("phone", "").strip(),
            "city": request.form.get("city", "").strip(),
        }
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if role not in ("parent", "teacher", "school"):
            flash("Account type not allowed.", "danger")
            return render_template("register.html", form=form, role=role)

        if not all(form.values()) or not password:
            flash("All fields are required.", "danger")
            return render_template("register.html", form=form, role=role)

        if not form["username"].replace("_", "").isalnum():
            flash("Username can only contain letters, numbers and underscores.",
                  "danger")
            return render_template("register.html", form=form, role=role)

        if len(form["phone"]) != 10 or not form["phone"].isdigit():
            flash("Please enter a valid 10-digit mobile number.", "danger")
            return render_template("register.html", form=form, role=role)

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return render_template("register.html", form=form, role=role)

        if password != confirm:
            flash("Passwords do not match.", "danger")
            return render_template("register.html", form=form, role=role)

        connection = db.get_db()
        if role == "parent":
            table, columns = "parent", "name, username, email, phone, city, password_hash"
            existing = connection.execute(
                "SELECT id FROM parent WHERE email = ? OR username = ?",
                (form["email"], form["username"]),
            ).fetchone()
        elif role == "teacher":
            table, columns = "teacher", "name, username, email, phone, city, password_hash"
            existing = connection.execute(
                "SELECT id FROM teacher WHERE email = ? OR username = ?",
                (form["email"], form["username"]),
            ).fetchone()
        else:
            table = "school"
            columns = (
                "name, username, email, phone, location, password_hash, "
                "syllabus, classes, fees"
            )
            existing = connection.execute(
                "SELECT id FROM school WHERE username = ? OR email = ?",
                (form["username"], form["email"]),
            ).fetchone()

        if existing is not None:
            flash("An account with this email or username already exists.",
                  "danger")
            return render_template("register.html", form=form, role=role)

        values = (
            form["full_name"],
            form["username"],
            form["email"],
            form["phone"],
            form["city"],
            generate_password_hash(password),
        )
        if role == "school":
            values = values + ("", "", "")
        connection.execute(
            f"INSERT INTO {table} ({columns}) VALUES (?, ?, ?, ?, ?, ?"
            + (", ?, ?, ?" if role == "school" else "")
            + ")",
            values,
        )
        connection.commit()

        flash("Registration successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form=form, role=role)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# =========================================
#  PARENT PAGES
# =========================================

@app.route("/parent/dashboard")
@parent_required
def parent_dashboard():
    parent = current_parent()
    stats = parent_stats(parent["id"])
    return render_template(
        "parent_dashboard.html", parent=parent, stats=stats,
    )


@app.route("/parent/child", methods=["GET", "POST"])
@parent_required
def parent_child():
    parent = current_parent()
    child = current_child(parent["id"])

    if request.method == "POST":
        child_name = request.form.get("child_name", "").strip()
        dob = request.form.get("dob", "").strip()
        gender = request.form.get("gender", "").strip()
        current_class = request.form.get("current_class", "").strip()
        location = request.form.get("location", "").strip()
        language = request.form.get("language", "english").strip()
        additional_info = request.form.get("additional_info", "").strip()

        if not child_name or not dob or not gender or not current_class or not location:
            flash("Please fill in all required child details.", "danger")
            return render_template("parent_child.html", parent=parent, child=child)

        connection = db.get_db()
        if child is not None:
            connection.execute(
                """
                UPDATE child SET child_name = ?, dob = ?, gender = ?,
                       current_class = ?, location = ?, language = ?,
                       additional_info = ?
                WHERE id = ?
                """,
                (child_name, dob, gender, current_class, location,
                 language, additional_info, child["id"]),
            )
            child_id = child["id"]
        else:
            cursor = connection.execute(
                """
                INSERT INTO child (parent_id, child_name, dob, gender,
                                   current_class, location, language,
                                   additional_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (parent["id"], child_name, dob, gender, current_class,
                 location, language, additional_info),
            )
            child_id = cursor.lastrowid

        generate_recommendations(child_id)
        connection.commit()

        flash("Child details saved successfully.", "success")
        return redirect(url_for("parent_dashboard"))

    return render_template("parent_child.html", parent=parent, child=child)


@app.route("/parent/assessment")
@parent_required
def parent_assessment():
    parent = current_parent()
    child = current_child(parent["id"])
    return render_template("parent_assessment.html", parent=parent, child=child)


@app.route("/parent/assessment/questions")
@parent_required
def assessment_questions():
    parent = current_parent()
    child = current_child(parent["id"])
    selected = []
    if child is not None:
        selected = select_questions_for_child(child)
        session["assessment_question_ids"] = [q["id"] for q in selected]
    return render_template(
        "assessment_questions.html",
        parent=parent,
        child=child,
        questions=selected,
    )


@app.route("/parent/assessment/submit", methods=["POST"])
@parent_required
def assessment_submit():
    parent = current_parent()
    if parent is None:
        return jsonify(
            {"success": False, "redirect": url_for("login")}
        )

    child = current_child(parent["id"])

    if child is None:
        flash("Please add your child details first.", "warning")
        return jsonify(
            {"success": False, "redirect": url_for("parent_child")}
        )

    data = request.get_json(silent=True) or {}
    answers = data.get("answers")
    question_ids = data.get("question_ids")

    if not isinstance(question_ids, list):
        question_ids = session.pop("assessment_question_ids", None)
    else:
        session.pop("assessment_question_ids", None)

    if (
        not isinstance(answers, list)
        or not isinstance(question_ids, list)
        or len(answers) != len(question_ids)
        or not question_ids
    ):
        return jsonify({"success": False, "error": "Invalid submission."}), 400

    bank = {q["id"]: q for q in QUIZ_QUESTIONS}
    selected = [bank[qid] for qid in question_ids if qid in bank]
    if len(selected) != len(question_ids):
        return jsonify({"success": False, "error": "Invalid submission."}), 400

    connection = db.get_db()

    correct = 0
    skill_correct = {name: 0 for name, _ in SKILLS}
    skill_asked = {name: 0 for name, _ in SKILLS}

    for index, question in enumerate(selected):
        skill = question["skill"]
        skill_asked[skill] += 1
        if answers[index] == question["answer"]:
            correct += 1
            skill_correct[skill] += 1

    total = len(selected)
    overall = round(correct / total * 100)

    cursor = connection.execute(
        "INSERT INTO assessment (child_id, status, overall_score, total_questions, completed_at) "
        "VALUES (?, 'completed', ?, ?, ?)",
        (
            child["id"],
            overall,
            total,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        ),
    )
    assessment_id = cursor.lastrowid

    connection.executemany(
        "INSERT INTO skill_score (assessment_id, skill, score, asked) "
        "VALUES (?, ?, ?, ?)",
        [
            (
                assessment_id,
                name,
                round(skill_correct[name] / skill_asked[name] * 100)
                if skill_asked[name]
                else 0,
                skill_asked[name],
            )
            for name, _ in SKILLS
        ],
    )

    generate_recommendations(child["id"])
    connection.commit()

    flash("Assessment submitted successfully! Your results are ready.", "success")
    return jsonify(
        {"success": True, "redirect": url_for("parent_results")}
    )


@app.route("/parent/results")
@parent_required
def parent_results():
    parent = current_parent()
    child = current_child(parent["id"])
    assessments = None
    assessment = None

    if child is not None:
        assessment = latest_assessment(child["id"])

    skills = [{"name": name, "icon": icon, "score": None, "asked": 0}
              for name, icon in SKILLS]
    total_questions = None

    if assessment is not None and assessment["status"] == "completed":
        total_questions = assessment["total_questions"]
        rows = db.get_db().execute(
            "SELECT skill, score, asked FROM skill_score "
            "WHERE assessment_id = ? ORDER BY id",
            (assessment["id"],),
        ).fetchall()
        assessments = [dict(row) for row in rows]
        score_map = {row["skill"]: row for row in assessments}
        for skill in skills:
            if row := score_map.get(skill["name"]):
                skill["score"] = row["score"]
                skill["asked"] = row["asked"]

    return render_template(
        "parent_results.html",
        parent=parent,
        child=child,
        assessment=assessment,
        skills=skills,
        assessments=assessments,
        total_questions=total_questions,
    )


@app.route("/parent/certificate")
@parent_required
def parent_certificate():
    parent = current_parent()
    child = current_child(parent["id"])
    assessment = None
    certificate = None

    if child is not None:
        assessment = certificate_ready(child["id"])

    if child is None or assessment is None:
        flash(
            "Complete the assessment to unlock your child's certificate.",
            "warning",
        )
        return redirect(url_for("parent_results"))

    certificate = get_or_create_certificate(child["id"], assessment["id"])
    total_questions = assessment["total_questions"]
    marks = round(assessment["overall_score"] / 100 * total_questions)

    return render_template(
        "parent_certificate.html",
        parent=parent,
        child=child,
        assessment=assessment,
        certificate=certificate,
        total_questions=total_questions,
        marks=marks,
    )


@app.route("/parent/observations")
@parent_required
def parent_observations():
    parent = current_parent()
    child = current_child(parent["id"])
    observations = []
    if child is not None:
        rows = db.get_db().execute(
            "SELECT o.*, t.name AS teacher_name, "
            "DATE(o.created_at) AS obs_date "
            "FROM teacher_observation o "
            "JOIN teacher t ON t.id = o.teacher_id "
            "WHERE o.child_id = ? "
            "ORDER BY o.created_at DESC",
            (child["id"],),
        ).fetchall()
        observations = [dict(row) for row in rows]
    return render_template(
        "parent_observations.html",
        parent=parent,
        child=child,
        observations=observations,
    )


@app.route("/parent/recommendations")
@parent_required
def parent_recommendations():
    parent = current_parent()
    child = current_child(parent["id"])
    recommendations = []
    admissions = {}
    teacher_recs = []
    teacher_rec_schools = set()

    if child is not None:
        conn = db.get_db()
        cur = conn.execute(
            """
            SELECT r.match_score, s.*
            FROM recommendation r
            JOIN school s ON s.id = r.school_id
            WHERE r.child_id = ?
            ORDER BY r.match_score DESC
            """,
            (child["id"],),
        )
        recommendations = [dict(row) for row in cur.fetchall()]
        for row in conn.execute(
            "SELECT * FROM admission WHERE child_id = ?", (child["id"],)
        ).fetchall():
            admissions[row["school_id"]] = dict(row)
        for row in conn.execute(
            "SELECT tr.*, t.name AS teacher_name, s.name AS school_name, "
            "s.location, s.syllabus, DATE(tr.created_at) AS rec_date "
            "FROM teacher_recommendation tr "
            "JOIN teacher t ON t.id = tr.teacher_id "
            "JOIN school s ON s.id = tr.school_id "
            "WHERE tr.child_id = ? ORDER BY tr.created_at DESC",
            (child["id"],),
        ).fetchall():
            row = dict(row)
            teacher_recs.append(row)
            teacher_rec_schools.add(row["school_id"])

    return render_template(
        "parent_recommendations.html",
        parent=parent,
        child=child,
        recommendations=recommendations,
        admissions=admissions,
        teacher_recs=teacher_recs,
        teacher_rec_schools=teacher_rec_schools,
    )


ADMISSION_STATUSES = [
    "Applied",
    "Documents Submitted",
    "Interview Scheduled",
    "Selected",
    "Admitted",
    "Rejected",
]


@app.route("/parent/admissions")
@parent_required
def parent_admissions():
    parent = current_parent()
    child = current_child(parent["id"])
    admissions = []
    if child is not None:
        rows = db.get_db().execute(
            """
            SELECT a.*, s.name AS school_name, s.location, s.syllabus, s.contact
            FROM admission a
            JOIN school s ON s.id = a.school_id
            WHERE a.child_id = ?
            ORDER BY a.updated_at DESC
            """,
            (child["id"],),
        ).fetchall()
        admissions = [dict(row) for row in rows]
    return render_template(
        "parent_admissions.html",
        parent=parent,
        child=child,
        admissions=admissions,
        statuses=ADMISSION_STATUSES,
    )


@app.route("/parent/admission/apply", methods=["POST"])
@parent_required
def admission_apply():
    parent = current_parent()
    child = current_child(parent["id"])
    if child is None:
        flash("Please add your child details first.", "warning")
        return redirect(url_for("parent_child"))
    school_id = request.form.get("school_id", type=int)
    if not school_id:
        flash("Please choose a school.", "danger")
        return redirect(url_for("parent_recommendations"))
    conn = db.get_db()
    existing = conn.execute(
        "SELECT id FROM admission WHERE child_id = ? AND school_id = ?",
        (child["id"], school_id),
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO admission (child_id, school_id, status, application_date) "
            "VALUES (?, ?, 'Applied', ?)",
            (
                child["id"],
                school_id,
                datetime.now().strftime("%Y-%m-%d"),
            ),
        )
        conn.commit()
        flash("Admission application created.", "success")
    else:
        flash("You already applied to this school.", "info")
    return redirect(url_for("parent_admission_view", school_id=school_id))


@app.route("/parent/admission/<int:school_id>", methods=["GET", "POST"])
@parent_required
def parent_admission_view(school_id):
    parent = current_parent()
    child = current_child(parent["id"])
    if child is None:
        flash("Please add your child details first.", "warning")
        return redirect(url_for("parent_child"))
    conn = db.get_db()
    school = conn.execute(
        "SELECT * FROM school WHERE id = ?", (school_id,)
    ).fetchone()
    if school is None:
        flash("School not found.", "danger")
        return redirect(url_for("parent_recommendations"))

    admission = conn.execute(
        "SELECT * FROM admission WHERE child_id = ? AND school_id = ?",
        (child["id"], school_id),
    ).fetchone()

    if request.method == "POST":
        status = request.form.get("status", "Applied").strip()
        application_date = request.form.get("application_date", "").strip()
        interview_date = request.form.get("interview_date", "").strip()
        documents = request.form.get("documents", "").strip()
        fee = request.form.get("fee", "").strip()
        contact = request.form.get("contact", "").strip()
        notes = request.form.get("notes", "").strip()

        if admission is None:
            conn.execute(
                "INSERT INTO admission (child_id, school_id, status, application_date, "
                "interview_date, documents, fee, contact, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (child["id"], school_id, status, application_date, interview_date,
                 documents, fee, contact, notes),
            )
            conn.commit()
            flash("Admission details saved.", "success")
        else:
            conn.execute(
                "UPDATE admission SET status=?, application_date=?, interview_date=?, "
                "documents=?, fee=?, contact=?, notes=?, updated_at=? "
                "WHERE id=?",
                (status, application_date, interview_date, documents, fee,
                 contact, notes, datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 admission["id"]),
            )
            conn.commit()
            flash("Admission details updated.", "success")
        return redirect(url_for("parent_admissions"))

    admission_data = dict(admission) if admission is not None else {
        "status": "Applied",
        "application_date": datetime.now().strftime("%Y-%m-%d"),
        "interview_date": "",
        "documents": "",
        "fee": "",
        "contact": "",
        "notes": "",
    }
    return render_template(
        "parent_admission.html",
        parent=parent,
        child=child,
        school=dict(school),
        admission=admission_data,
        statuses=ADMISSION_STATUSES,
    )


@app.route("/parent/admission/<int:school_id>/delete", methods=["POST"])
@parent_required
def admission_delete(school_id):
    parent = current_parent()
    child = current_child(parent["id"])
    if child is not None:
        conn = db.get_db()
        conn.execute(
            "DELETE FROM admission WHERE child_id = ? AND school_id = ?",
            (child["id"], school_id),
        )
        conn.commit()
        flash("Admission application removed.", "info")
    return redirect(url_for("parent_recommendations"))


CAP_STEPS = [
    ("Check Eligibility",
     "Confirm that the child meets the age, class and syllabus eligibility criteria for admission."),
    ("CET / Entrance Exam",
     "Appear for the Common Entrance Test (CET) or the school's entrance examination."),
    ("CET Result / Score",
     "Check the CET / entrance exam result and note down the score."),
    ("CAP Registration - Fill Online Application",
     "Register on the CAP (Centralised Admission Process) portal and fill the online application form."),
    ("Upload Required Documents",
     "Upload all required documents such as birth certificate, address proof, previous marksheet and photo."),
    ("Document Verification",
     "Documents are verified at the facilitation centre / school office."),
    ("Application Confirmation",
     "Online application is confirmed after successful verification."),
    ("Provisional Merit List",
     "Provisional merit list is published on the portal."),
    ("Final Merit List Published",
     "Final merit list is published after objections are resolved."),
    ("Fill Option Form (College + Course Choice)",
     "Fill the option form with preferred colleges and courses in order of choice."),
    ("CAP Round I",
     "Seat allotment is processed based on merit and option form (Round I)."),
    ("Seat Allotment Result",
     "Check the seat allotment result for the current round."),
    ("Self Verification / Accept Seat",
     "If the seat is accepted, complete self-verification. If not accepted, wait for the next CAP round."),
    ("Report to College",
     "Report to the allotted college with the allotment letter and required documents."),
    ("Confirm Admission (END)",
     "Admission is confirmed. Collect the admission confirmation receipt."),
]


def ensure_admission_steps(conn, admission_id):
    count = conn.execute(
        "SELECT COUNT(*) FROM admission_step WHERE admission_id = ?",
        (admission_id,),
    ).fetchone()[0]
    if count == 0:
        conn.executemany(
            "INSERT INTO admission_step (admission_id, step_key, step_name, step_order) "
            "VALUES (?, ?, ?, ?)",
            [(admission_id, str(i + 1), name, i + 1)
             for i, (name, _desc) in enumerate(CAP_STEPS)],
        )
        conn.commit()


@app.route("/parent/admission/<int:school_id>/process", methods=["GET", "POST"])
@parent_required
def parent_admission_process(school_id):
    parent = current_parent()
    child = current_child(parent["id"])
    if child is None:
        flash("Please add your child details first.", "warning")
        return redirect(url_for("parent_child"))

    conn = db.get_db()
    school = conn.execute(
        "SELECT * FROM school WHERE id = ?", (school_id,)
    ).fetchone()
    if school is None:
        flash("School not found.", "danger")
        return redirect(url_for("parent_recommendations"))

    admission = conn.execute(
        "SELECT * FROM admission WHERE child_id = ? AND school_id = ?",
        (child["id"], school_id),
    ).fetchone()
    if admission is None:
        conn.execute(
            "INSERT INTO admission (child_id, school_id, status, application_date) "
            "VALUES (?, ?, 'Applied', ?)",
            (child["id"], school_id, datetime.now().strftime("%Y-%m-%d")),
        )
        conn.commit()
        admission = conn.execute(
            "SELECT * FROM admission WHERE child_id = ? AND school_id = ?",
            (child["id"], school_id),
        ).fetchone()
        flash("Admission application created. You can now track the process.", "success")

    if request.method == "POST":
        action = request.form.get("action", "")
        step_id = request.form.get("step_id", type=int)
        step_data = request.form.get("step_data", "").strip()
        if step_id:
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if action == "complete":
                conn.execute(
                    "UPDATE admission_step SET status = 'completed', completed_at = ? "
                    "WHERE id = ? AND admission_id = ?",
                    (now, step_id, admission["id"]),
                )
                flash("Step marked as completed.", "success")
            elif action == "undo":
                conn.execute(
                    "UPDATE admission_step SET status = 'pending', completed_at = '' "
                    "WHERE id = ? AND admission_id = ?",
                    (step_id, admission["id"]),
                )
                flash("Step marked as pending.", "info")
            elif action == "save":
                conn.execute(
                    "UPDATE admission_step SET step_data = ? "
                    "WHERE id = ? AND admission_id = ?",
                    (step_data, step_id, admission["id"]),
                )
                flash("Step details saved.", "success")
            conn.commit()
        return redirect(url_for("parent_admission_process", school_id=school_id))

    ensure_admission_steps(conn, admission["id"])
    steps = conn.execute(
        "SELECT * FROM admission_step WHERE admission_id = ? ORDER BY step_order",
        (admission["id"],),
    ).fetchall()
    steps = [dict(row) for row in steps]
    completed = sum(1 for s in steps if s["status"] == "completed")
    total = len(steps)
    percent = round(completed / total * 100) if total else 0

    return render_template(
        "parent_admission_process.html",
        parent=parent,
        child=child,
        school=dict(school),
        admission=dict(admission),
        steps=steps,
        completed=completed,
        total=total,
        percent=percent,
    )


@app.route("/parent/profile", methods=["GET", "POST"])
@parent_required
def parent_profile():
    parent = current_parent()

    if request.method == "POST":
        name = request.form.get("parent_name", "").strip()
        email = request.form.get("parent_email", "").strip().lower()
        phone = request.form.get("parent_phone", "").strip()
        city = request.form.get("parent_city", "").strip()
        contact_time = request.form.get("contact_time", "evening").strip()
        language = request.form.get("parent_language", "english").strip()
        additional_info = request.form.get("parent_info", "").strip()

        if not name or not email or not phone or not city:
            flash("Please fill in all required profile fields.", "danger")
            return render_template("parent_profile.html", parent=parent)

        if len(phone) != 10 or not phone.isdigit():
            flash("Please enter a valid 10-digit mobile number.", "danger")
            return render_template("parent_profile.html", parent=parent)

        connection = db.get_db()
        duplicate = connection.execute(
            "SELECT id FROM parent WHERE email = ? AND id != ?",
            (email, parent["id"]),
        ).fetchone()
        if duplicate is not None:
            flash("This email is already in use.", "danger")
            return render_template("parent_profile.html", parent=parent)

        connection.execute(
            """
            UPDATE parent SET name = ?, email = ?, phone = ?, city = ?,
                   contact_time = ?, language = ?, additional_info = ?
            WHERE id = ?
            """,
            (name, email, phone, city, contact_time, language,
             additional_info, parent["id"]),
        )
        connection.commit()

        flash("Profile updated successfully.", "success")
        return redirect(url_for("parent_profile"))

    return render_template("parent_profile.html", parent=parent)


# =========================================
#  TEACHER PAGES
# =========================================

@app.route("/teacher/dashboard")
@teacher_required
def teacher_dashboard():
    teacher = current_teacher()
    conn = db.get_db()
    assigned = conn.execute(
        "SELECT c.* FROM child c "
        "JOIN teacher_child tc ON tc.child_id = c.id "
        "WHERE tc.teacher_id = ? ORDER BY tc.created_at DESC",
        (teacher["id"],),
    ).fetchall()
    observation_count = conn.execute(
        "SELECT COUNT(*) AS n FROM teacher_observation WHERE teacher_id = ?",
        (teacher["id"],),
    ).fetchone()["n"]
    return render_template(
        "teacher_dashboard.html",
        teacher=teacher,
        children=[dict(r) for r in assigned],
        observation_count=observation_count,
    )


@app.route("/teacher/children")
@teacher_required
def teacher_children():
    teacher = current_teacher()
    conn = db.get_db()
    assigned = conn.execute(
        "SELECT c.*, tc.id AS assignment_id FROM child c "
        "JOIN teacher_child tc ON tc.child_id = c.id "
        "WHERE tc.teacher_id = ? ORDER BY c.child_name",
        (teacher["id"],),
    ).fetchall()
    all_children = conn.execute(
        "SELECT c.*, p.name AS parent_name "
        "FROM child c JOIN parent p ON p.id = c.parent_id "
        "ORDER BY c.child_name"
    ).fetchall()
    return render_template(
        "teacher_children.html",
        teacher=teacher,
        assigned=[dict(r) for r in assigned],
        all_children=[dict(r) for r in all_children],
    )


@app.route("/teacher/assign", methods=["POST"])
@teacher_required
def teacher_assign():
    teacher = current_teacher()
    child_id = request.form.get("child_id", type=int)
    if child_id:
        conn = db.get_db()
        existing = conn.execute(
            "SELECT id FROM teacher_child WHERE teacher_id = ? AND child_id = ?",
            (teacher["id"], child_id),
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO teacher_child (teacher_id, child_id) VALUES (?, ?)",
                (teacher["id"], child_id),
            )
            conn.commit()
            flash("Child assigned successfully.", "success")
    return redirect(url_for("teacher_children"))


@app.route("/teacher/observation", methods=["GET", "POST"])
@teacher_required
def teacher_observation():
    teacher = current_teacher()
    conn = db.get_db()
    children = conn.execute(
        "SELECT c.* FROM child c "
        "JOIN teacher_child tc ON tc.child_id = c.id "
        "WHERE tc.teacher_id = ? ORDER BY c.child_name",
        (teacher["id"],),
    ).fetchall()
    if request.method == "POST":
        child_id = request.form.get("child_id", type=int)
        skill = request.form.get("skill", "").strip()
        rating = request.form.get("rating", type=int)
        remarks = request.form.get("remarks", "").strip()
        if not child_id or not skill or not rating:
            flash("Please fill all required fields.", "danger")
            return render_template(
                "teacher_observation.html",
                teacher=teacher,
                children=[dict(r) for r in children],
                skills=SKILLS,
            )
        conn.execute(
            "INSERT INTO teacher_observation (teacher_id, child_id, skill, rating, remarks) "
            "VALUES (?, ?, ?, ?, ?)",
            (teacher["id"], child_id, skill, rating, remarks),
        )
        generate_recommendations(child_id)
        conn.commit()
        flash("Observation recorded successfully.", "success")
        return redirect(url_for("teacher_observations_list"))
    return render_template(
        "teacher_observation.html",
        teacher=teacher,
        children=[dict(r) for r in children],
        skills=SKILLS,
    )


@app.route("/teacher/observations")
@teacher_required
def teacher_observations_list():
    teacher = current_teacher()
    rows = db.get_db().execute(
        "SELECT o.*, c.child_name, c.parent_id, DATE(o.created_at) AS date "
        "FROM teacher_observation o "
        "JOIN child c ON c.id = o.child_id "
        "WHERE o.teacher_id = ? ORDER BY o.created_at DESC",
        (teacher["id"],),
    ).fetchall()
    return render_template(
        "teacher_observations.html",
        teacher=teacher,
        observations=[dict(r) for r in rows],
    )


@app.route("/teacher/recommend", methods=["GET", "POST"])
@teacher_required
def teacher_recommend():
    teacher = current_teacher()
    conn = db.get_db()
    children = conn.execute(
        "SELECT c.* FROM child c "
        "JOIN teacher_child tc ON tc.child_id = c.id "
        "WHERE tc.teacher_id = ? ORDER BY c.child_name",
        (teacher["id"],),
    ).fetchall()

    saved = conn.execute(
        "SELECT child_id, school_id FROM teacher_recommendation "
        "WHERE teacher_id = ?",
        (teacher["id"],),
    ).fetchall()
    child_school_map = {}
    for row in saved:
        child_school_map.setdefault(row["child_id"], set()).add(row["school_id"])

    if request.method == "POST":
        child_id = request.form.get("child_id", type=int)
        school_ids = request.form.getlist("school_ids")
        note = request.form.get("note", "").strip()
        if not child_id:
            flash("Please select a child.", "danger")
            return redirect(url_for("teacher_recommend"))
        assigned = conn.execute(
            "SELECT c.id FROM child c "
            "JOIN teacher_child tc ON tc.child_id = c.id "
            "WHERE tc.teacher_id = ? AND c.id = ?",
            (teacher["id"], child_id),
        ).fetchone()
        if assigned is None:
            flash("This child is not assigned to you.", "danger")
            return redirect(url_for("teacher_recommend"))
        conn.execute(
            "DELETE FROM teacher_recommendation "
            "WHERE teacher_id = ? AND child_id = ?",
            (teacher["id"], child_id),
        )
        for school_id in school_ids:
            school_id = school_id.strip()
            if school_id.isdigit():
                conn.execute(
                    "INSERT INTO teacher_recommendation "
                    "(teacher_id, child_id, school_id, note) "
                    "VALUES (?, ?, ?, ?)",
                    (teacher["id"], child_id, int(school_id), note),
                )
        conn.commit()
        flash("School recommendation saved.", "success")
        return redirect(url_for("teacher_recommend", child_id=child_id))

    children_list = [dict(r) for r in children]
    selected_child_id = request.args.get("child_id", type=int)
    if selected_child_id not in {c["id"] for c in children_list}:
        selected_child_id = children_list[0]["id"] if children_list else None

    saved_schools = set()
    if selected_child_id is not None:
        saved_schools = set(child_school_map.get(selected_child_id, set()))
    selected_schools = set(saved_schools)
    for sid in request.args.getlist("school_ids"):
        if sid.isdigit():
            selected_schools.add(int(sid))

    q = request.args.get("q", "").strip()
    per_page = 10
    page = request.args.get("page", 1, type=int) or 1

    where = ""
    params = []
    if q:
        where = (
            "WHERE LOWER(name) LIKE ? OR LOWER(location) LIKE ? "
            "OR LOWER(syllabus) LIKE ? OR LOWER(classes) LIKE ?"
        )
        pattern = f"%{q.lower()}%"
        params = [pattern, pattern, pattern, pattern]

    total = conn.execute(
        f"SELECT COUNT(*) FROM school {where}", params
    ).fetchone()[0]
    total_pages = max(1, math.ceil(total / per_page))
    page = min(max(page, 1), total_pages)

    schools = conn.execute(
        f"SELECT * FROM school {where} "
        "ORDER BY location, name LIMIT ? OFFSET ?",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    return render_template(
        "teacher_recommend.html",
        teacher=teacher,
        children=children_list,
        schools=[dict(r) for r in schools],
        selected_child_id=selected_child_id,
        selected_schools=selected_schools,
        q=q,
        page=page,
        total_pages=total_pages,
        total=total,
        per_page=per_page,
    )


@app.route("/teacher/recommendations")
@teacher_required
def teacher_recommendations_list():
    teacher = current_teacher()
    rows = db.get_db().execute(
        "SELECT tr.*, c.child_name, s.name AS school_name, s.location, s.syllabus, "
        "DATE(tr.created_at) AS rec_date "
        "FROM teacher_recommendation tr "
        "JOIN child c ON c.id = tr.child_id "
        "JOIN school s ON s.id = tr.school_id "
        "WHERE tr.teacher_id = ? ORDER BY tr.created_at DESC",
        (teacher["id"],),
    ).fetchall()
    return render_template(
        "teacher_recommendations.html",
        teacher=teacher,
        recommendations=[dict(r) for r in rows],
    )


@app.route("/teacher/recommendations/delete", methods=["POST"])
@teacher_required
def teacher_recommendations_delete():
    recommendation_id = request.form.get("recommendation_id", type=int)
    if recommendation_id:
        conn = db.get_db()
        conn.execute(
            "DELETE FROM teacher_recommendation WHERE id = ? AND teacher_id = ?",
            (recommendation_id, current_teacher()["id"]),
        )
        conn.commit()
        flash("Recommendation removed.", "info")
    return redirect(url_for("teacher_recommendations_list"))


# =========================================
#  SCHOOL PAGES
# =========================================

ADMISSION_SCORE_THRESHOLD = 70


@app.route("/school/dashboard")
@school_required
def school_dashboard():
    school = current_school()
    conn = db.get_db()
    recommendation_count = conn.execute(
        "SELECT COUNT(*) AS n FROM recommendation WHERE school_id = ?",
        (school["id"],),
    ).fetchone()["n"]

    rows = conn.execute(
        """
        SELECT a.id AS admission_id, a.status, a.application_date, a.interview_date,
               c.child_name, c.current_class, c.id AS child_id,
               p.name AS parent_name, p.phone AS parent_phone
        FROM admission a
        JOIN child c ON c.id = a.child_id
        JOIN parent p ON p.id = c.parent_id
        WHERE a.school_id = ?
        ORDER BY a.updated_at DESC
        """,
        (school["id"],),
    ).fetchall()

    applied = []
    for row in rows:
        item = dict(row)
        item["readiness"] = child_readiness(conn, item["child_id"])
        latest = conn.execute(
            "SELECT overall_score FROM assessment "
            "WHERE child_id = ? AND status = 'completed' "
            "ORDER BY id DESC LIMIT 1",
            (item["child_id"],),
        ).fetchone()
        item["overall_score"] = latest["overall_score"] if latest else None
        applied.append(item)

    return render_template(
        "school_dashboard.html",
        school=school,
        recommendation_count=recommendation_count,
        applied=applied,
        threshold=ADMISSION_SCORE_THRESHOLD,
    )


@app.route("/school/admission/<int:admission_id>/status", methods=["POST"])
@school_required
def school_admission_status(admission_id):
    school = current_school()
    conn = db.get_db()
    row = conn.execute(
        "SELECT a.id, a.child_id, a.status, a.school_id, c.child_name "
        "FROM admission a JOIN child c ON c.id = a.child_id "
        "WHERE a.id = ?",
        (admission_id,),
    ).fetchone()
    if row is None or row["school_id"] != school["id"]:
        flash("Admission application not found.", "danger")
        return redirect(url_for("school_dashboard"))

    action = request.form.get("action", "").strip()
    readiness = child_readiness(conn, row["child_id"])

    status_map = {
        "interview": "Interview Scheduled",
        "select": "Selected",
        "admit": "Admitted",
        "reject": "Rejected",
    }
    if action not in status_map:
        flash("Invalid action.", "danger")
        return redirect(url_for("school_dashboard"))

    new_status = status_map[action]

    if action in ("select", "admit") and readiness < ADMISSION_SCORE_THRESHOLD:
        flash(
            f"{row['child_name']}'s readiness score is {readiness}% — "
            f"below the {ADMISSION_SCORE_THRESHOLD}% threshold. "
            "This student cannot be selected.",
            "warning",
        )
        return redirect(url_for("school_dashboard"))

    if action == "interview":
        interview_date = request.form.get("interview_date", "").strip()
    else:
        interview_date = conn.execute(
            "SELECT interview_date FROM admission WHERE id = ?",
            (admission_id,),
        ).fetchone()["interview_date"]

    conn.execute(
        "UPDATE admission SET status = ?, interview_date = ?, updated_at = ? "
        "WHERE id = ?",
        (
            new_status,
            interview_date,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            admission_id,
        ),
    )
    conn.commit()
    flash(
        f"Admission for {row['child_name']} marked as '{new_status}'.",
        "success",
    )
    return redirect(url_for("school_dashboard"))


@app.route("/school/profile", methods=["GET", "POST"])
@school_required
def school_profile():
    school = current_school()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        syllabus = request.form.get("syllabus", "").strip()
        classes = request.form.get("classes", "").strip()
        fees = request.form.get("fees", "").strip()
        facilities = request.form.get("facilities", "").strip()
        methodology = request.form.get("methodology", "").strip()
        contact = request.form.get("contact", "").strip()
        if not name or not syllabus:
            flash("School name and syllabus are required.", "danger")
            return render_template("school_profile.html", school=school)

        connection = db.get_db()

        settings_sql = ["name=?", "syllabus=?", "classes=?", "fees=?",
                        "facilities=?", "methodology=?", "contact=?"]
        settings_values = [name, syllabus, classes, fees, facilities,
                           methodology, contact]

        if not school["username"]:
            username = request.form.get("username", "").strip().lower()
            email = request.form.get("email", "").strip().lower()
            phone = request.form.get("phone", "").strip()
            new_password = request.form.get("new_password", "")

            if username:
                if not username.replace("_", "").isalnum():
                    flash(
                        "Username can only contain letters, numbers and "
                        "underscores.",
                        "danger",
                    )
                    return render_template("school_profile.html", school=school)
                clash = connection.execute(
                    "SELECT id FROM school WHERE username = ? AND id != ?",
                    (username, school["id"]),
                ).fetchone()
                if clash is not None:
                    flash("That username is already in use.", "danger")
                    return render_template("school_profile.html", school=school)
                if email:
                    clash = connection.execute(
                        "SELECT id FROM school WHERE email = ? AND id != ?",
                        (email, school["id"]),
                    ).fetchone()
                    if clash is not None:
                        flash("That email is already in use.", "danger")
                        return render_template("school_profile.html", school=school)

            if new_password:
                if len(new_password) < 6:
                    flash("New password must be at least 6 characters.", "danger")
                    return render_template("school_profile.html", school=school)

            if username:
                settings_sql.append("username=?")
                settings_values.append(username)
            if email:
                settings_sql.append("email=?")
                settings_values.append(email)
            if phone:
                settings_sql.append("phone=?")
                settings_values.append(phone)
            if new_password:
                settings_sql.append("password_hash=?")
                settings_values.append(generate_password_hash(new_password))

        settings_values.append(school["id"])
        connection.execute(
            "UPDATE school SET "
            + ", ".join(settings_sql)
            + " WHERE id=?",
            settings_values,
        )
        connection.commit()
        flash("School profile updated.", "success")
        return redirect(url_for("school_dashboard"))
    return render_template("school_profile.html", school=school)


# =========================================
#  ADMIN PAGES
# =========================================

@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    admin = current_admin()
    conn = db.get_db()
    counts = {
        "parents": conn.execute("SELECT COUNT(*) FROM parent").fetchone()[0],
        "teachers": conn.execute("SELECT COUNT(*) FROM teacher").fetchone()[0],
        "schools": conn.execute("SELECT COUNT(*) FROM school").fetchone()[0],
        "children": conn.execute("SELECT COUNT(*) FROM child").fetchone()[0],
        "assessments": conn.execute("SELECT COUNT(*) FROM assessment").fetchone()[0],
    }
    children = conn.execute(
        """
        SELECT c.id, c.child_name, c.current_class, c.location,
               p.name AS parent_name,
               a.status AS assessment_status,
               a.overall_score AS assessment_score,
               (SELECT GROUP_CONCAT(t.name, ', ')
                  FROM teacher_child tc
                  JOIN teacher t ON t.id = tc.teacher_id
                 WHERE tc.child_id = c.id) AS teachers,
               (SELECT COUNT(*) FROM recommendation r
                 WHERE r.child_id = c.id) AS rec_count,
               (SELECT ad.status FROM admission ad
                 WHERE ad.child_id = c.id
                 ORDER BY ad.updated_at DESC LIMIT 1) AS admission_status
          FROM child c
          JOIN parent p ON p.id = c.parent_id
          LEFT JOIN assessment a ON a.id = (
              SELECT id FROM assessment
               WHERE child_id = c.id
               ORDER BY created_at DESC LIMIT 1)
         ORDER BY c.created_at DESC
        """
    ).fetchall()
    return render_template(
        "admin_dashboard.html",
        admin=admin, counts=counts,
        children=[dict(r) for r in children],
    )


@app.route("/admin/children")
@admin_required
def admin_children():
    admin = current_admin()
    rows = db.get_db().execute(
        "SELECT c.*, p.name AS parent_name FROM child c "
        "JOIN parent p ON p.id = c.parent_id ORDER BY c.child_name"
    ).fetchall()
    return render_template("admin_children.html", admin=admin, children=[dict(r) for r in rows])


@app.route("/admin/teachers", methods=["GET", "POST"])
@admin_required
def admin_teachers():
    admin = current_admin()
    conn = db.get_db()
    if request.method == "POST":
        if request.form.get("action") == "reset":
            teacher_id = request.form.get("teacher_id", type=int)
            username = request.form.get("username", "").strip().lower()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            if not teacher_id:
                flash("Missing teacher ID.", "danger")
            elif not username or not email or not password:
                flash("Username, email and password are all required.", "danger")
            elif not username.replace("_", "").isalnum():
                flash(
                    "Username can only contain letters, numbers and underscores.",
                    "danger",
                )
            elif len(password) < 6:
                flash("Password must be at least 6 characters.", "danger")
            else:
                clash = conn.execute(
                    "SELECT id FROM teacher WHERE (username = ? OR email = ?) "
                    "AND id != ?",
                    (username, email, teacher_id),
                ).fetchone()
                if clash is not None:
                    flash("Another teacher is already using that username or email.",
                          "danger")
                else:
                    conn.execute(
                        "UPDATE teacher SET username=?, email=?, password_hash=? "
                        "WHERE id=?",
                        (username, email, generate_password_hash(password),
                         teacher_id),
                    )
                    conn.commit()
                    flash("Teacher login credentials updated.", "success")
            return redirect(url_for("admin_teachers"))

        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        qualification = request.form.get("qualification", "").strip()
        experience = request.form.get("experience", "").strip()
        password = request.form.get("password", "")
        if not all([name, username, email, phone, city, password]):
            flash("Name, username, email, phone, city and password are required.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            existing = conn.execute(
                "SELECT id FROM teacher WHERE username = ? OR email = ?",
                (username, email),
            ).fetchone()
            if existing is not None:
                flash("A teacher with this username or email already exists.", "danger")
            else:
                conn.execute(
                    "INSERT INTO teacher (name, username, email, phone, city, "
                    "qualification, experience, password_hash) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (name, username, email, phone, city, qualification, experience,
                     generate_password_hash(password)),
                )
                conn.commit()
                flash(f"Teacher '{name}' added successfully.", "success")
        return redirect(url_for("admin_teachers"))
    rows = conn.execute(
        "SELECT * FROM teacher ORDER BY created_at DESC"
    ).fetchall()
    return render_template("admin_teachers.html", admin=admin, teachers=[dict(r) for r in rows])


@app.route("/admin/parents", methods=["GET", "POST"])
@admin_required
def admin_parents():
    admin = current_admin()
    conn = db.get_db()
    if request.method == "POST":
        parent_id = request.form.get("parent_id", type=int)
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not parent_id:
            flash("Missing parent ID.", "danger")
        elif not username or not email or not password:
            flash("Username, email and password are all required.", "danger")
        elif not username.replace("_", "").isalnum():
            flash(
                "Username can only contain letters, numbers and underscores.",
                "danger",
            )
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            clash = conn.execute(
                "SELECT id FROM parent WHERE (username = ? OR email = ?) "
                "AND id != ?",
                (username, email, parent_id),
            ).fetchone()
            if clash is not None:
                flash("Another parent is already using that username or email.",
                      "danger")
            else:
                conn.execute(
                    "UPDATE parent SET username=?, email=?, password_hash=? "
                    "WHERE id=?",
                    (username, email, generate_password_hash(password), parent_id),
                )
                conn.commit()
                flash("Parent login credentials updated.", "success")
        return redirect(url_for("admin_parents"))

    rows = conn.execute(
        "SELECT p.*, "
        "(SELECT COUNT(*) FROM child c WHERE c.parent_id = p.id) AS child_count "
        "FROM parent p ORDER BY p.created_at DESC"
    ).fetchall()
    return render_template("admin_parents.html", admin=admin, parents=[dict(r) for r in rows])


@app.route("/admin/parent/<int:parent_id>")
@admin_required
def admin_parent_detail(parent_id):
    admin = current_admin()
    conn = db.get_db()
    parent = conn.execute(
        "SELECT * FROM parent WHERE id = ?", (parent_id,)
    ).fetchone()
    if parent is None:
        flash("Parent not found.", "danger")
        return redirect(url_for("admin_parents"))
    children = conn.execute(
        "SELECT * FROM child WHERE parent_id = ? ORDER BY child_name",
        (parent_id,),
    ).fetchall()
    return render_template(
        "admin_parent_detail.html",
        admin=admin,
        parent=dict(parent),
        children=[dict(r) for r in children],
    )


@app.route("/admin/teacher/<int:teacher_id>")
@admin_required
def admin_teacher_detail(teacher_id):
    admin = current_admin()
    conn = db.get_db()
    teacher = conn.execute(
        "SELECT * FROM teacher WHERE id = ?", (teacher_id,)
    ).fetchone()
    if teacher is None:
        flash("Teacher not found.", "danger")
        return redirect(url_for("admin_teachers"))
    children = conn.execute(
        "SELECT c.*, p.name AS parent_name "
        "FROM child c "
        "JOIN teacher_child tc ON tc.child_id = c.id "
        "JOIN parent p ON p.id = c.parent_id "
        "WHERE tc.teacher_id = ? ORDER BY c.child_name",
        (teacher_id,),
    ).fetchall()
    return render_template(
        "admin_teacher_detail.html",
        admin=admin,
        teacher=dict(teacher),
        children=[dict(r) for r in children],
    )


@app.route("/admin/school/<int:school_id>")
@admin_required
def admin_school_detail(school_id):
    admin = current_admin()
    conn = db.get_db()
    school = conn.execute(
        "SELECT * FROM school WHERE id = ?", (school_id,)
    ).fetchone()
    if school is None:
        flash("School not found.", "danger")
        return redirect(url_for("admin_schools"))
    admissions = conn.execute(
        "SELECT a.id, a.status, a.application_date, a.interview_date, "
        "c.child_name, p.name AS parent_name "
        "FROM admission a "
        "JOIN child c ON c.id = a.child_id "
        "JOIN parent p ON p.id = c.parent_id "
        "WHERE a.school_id = ? ORDER BY a.updated_at DESC",
        (school_id,),
    ).fetchall()
    recommendation_count = conn.execute(
        "SELECT COUNT(*) FROM recommendation WHERE school_id = ?",
        (school_id,),
    ).fetchone()[0]
    return render_template(
        "admin_school_detail.html",
        admin=admin,
        school=dict(school),
        admissions=[dict(r) for r in admissions],
        recommendation_count=recommendation_count,
    )


@app.route("/admin/schools", methods=["GET", "POST"])
@admin_required
def admin_schools():
    admin = current_admin()
    conn = db.get_db()

    if request.method == "POST" and request.form.get("action") == "reset":
        school_id = request.form.get("school_id", type=int)
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not school_id:
            flash("Missing school ID.", "danger")
            return redirect(url_for("admin_schools"))
        if not username or not email or not password:
            flash("Username, email and password are all required.", "danger")
            return redirect(url_for("admin_schools"))
        if not username.replace("_", "").isalnum():
            flash(
                "Username can only contain letters, numbers and underscores.",
                "danger",
            )
            return redirect(url_for("admin_schools"))
        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("admin_schools"))

        clash = conn.execute(
            "SELECT id FROM school WHERE (username = ? OR email = ?) "
            "AND id != ?",
            (username, email, school_id),
        ).fetchone()
        if clash is not None:
            flash("Another school is already using that username or email.",
                  "danger")
            return redirect(url_for("admin_schools"))

        conn.execute(
            "UPDATE school SET username=?, email=?, password_hash=? WHERE id=?",
            (username, email, generate_password_hash(password), school_id),
        )
        conn.commit()
        flash("School login credentials updated.", "success")
        return redirect(url_for("admin_schools"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip().lower()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        location = request.form.get("location", "").strip()
        syllabus = request.form.get("syllabus", "General").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not username or not email or not location or not password:
            flash("All fields are required.", "danger")
            return redirect(url_for("admin_schools"))

        if not username.replace("_", "").isalnum():
            flash(
                "Username can only contain letters, numbers and underscores.",
                "danger",
            )
            return redirect(url_for("admin_schools"))

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
            return redirect(url_for("admin_schools"))

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(url_for("admin_schools"))

        existing = conn.execute(
            "SELECT id FROM school WHERE username = ? OR email = ?",
            (username, email),
        ).fetchone()
        if existing is not None:
            flash("A school with this username or email already exists.", "danger")
            return redirect(url_for("admin_schools"))

        conn.execute(
            "INSERT INTO school (name, username, email, phone, location, "
            "syllabus, classes, fees, rating, password_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, '', '', 0, ?)",
            (name, username, email, phone, location, syllabus,
             generate_password_hash(password)),
        )
        conn.commit()
        flash("School account created successfully.", "success")
        return redirect(url_for("admin_schools"))

    rows = conn.execute(
        "SELECT * FROM school ORDER BY location, name"
    ).fetchall()
    return render_template("admin_schools.html", admin=admin, schools=[dict(r) for r in rows])


@app.route("/admin/assessments")
@admin_required
def admin_assessments():
    admin = current_admin()
    rows = db.get_db().execute(
        "SELECT a.*, c.child_name, p.name AS parent_name "
        "FROM assessment a "
        "JOIN child c ON c.id = a.child_id "
        "JOIN parent p ON p.id = c.parent_id "
        "ORDER BY a.created_at DESC"
    ).fetchall()
    return render_template(
        "admin_assessments.html", admin=admin,
        assessments=[dict(r) for r in rows],
    )


@app.route("/admin/assign", methods=["GET", "POST"])
@admin_required
def admin_assign():
    admin = current_admin()
    conn = db.get_db()
    children = conn.execute(
        "SELECT c.*, p.name AS parent_name FROM child c "
        "JOIN parent p ON p.id = c.parent_id ORDER BY c.child_name"
    ).fetchall()
    teachers = conn.execute(
        "SELECT * FROM teacher ORDER BY name"
    ).fetchall()
    assignments = conn.execute(
        "SELECT tc.*, t.name AS teacher_name, c.child_name "
        "FROM teacher_child tc "
        "JOIN teacher t ON t.id = tc.teacher_id "
        "JOIN child c ON c.id = tc.child_id "
        "ORDER BY t.name, c.child_name"
    ).fetchall()
    if request.method == "POST":
        teacher_id = request.form.get("teacher_id", type=int)
        child_id = request.form.get("child_id", type=int)
        if teacher_id and child_id:
            existing = conn.execute(
                "SELECT id FROM teacher_child WHERE teacher_id = ? AND child_id = ?",
                (teacher_id, child_id),
            ).fetchone()
            if existing is None:
                conn.execute(
                    "INSERT INTO teacher_child (teacher_id, child_id) VALUES (?, ?)",
                    (teacher_id, child_id),
                )
                conn.commit()
                flash("Assignment created.", "success")
        return redirect(url_for("admin_assign"))
    return render_template(
        "admin_assign.html",
        admin=admin,
        children=[dict(r) for r in children],
        teachers=[dict(r) for r in teachers],
        assignments=[dict(r) for r in assignments],
    )


@app.route("/admin/assign/delete", methods=["POST"])
@admin_required
def admin_assign_delete():
    assignment_id = request.form.get("assignment_id", type=int)
    if assignment_id:
        db.get_db().execute("DELETE FROM teacher_child WHERE id = ?", (assignment_id,))
        db.get_db().commit()
        flash("Assignment removed.", "info")
    return redirect(url_for("admin_assign"))


if __name__ == "__main__":
    app.run(debug=True)