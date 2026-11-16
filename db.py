import os
import re
import sqlite3

from flask import g
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "edumentor.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS parent (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL,
    city TEXT NOT NULL,
    contact_time TEXT DEFAULT 'evening',
    language TEXT DEFAULT 'english',
    additional_info TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS child (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id INTEGER NOT NULL REFERENCES parent(id) ON DELETE CASCADE,
    child_name TEXT NOT NULL,
    dob TEXT NOT NULL,
    gender TEXT NOT NULL,
    current_class TEXT NOT NULL,
    location TEXT NOT NULL,
    language TEXT NOT NULL,
    additional_info TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS assessment (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'pending',
    overall_score REAL DEFAULT 0,
    total_questions INTEGER DEFAULT 16,
    completed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skill_score (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    assessment_id INTEGER NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    score REAL DEFAULT 0,
    asked INTEGER DEFAULT 2
);

CREATE TABLE IF NOT EXISTS school (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    location TEXT NOT NULL,
    syllabus TEXT NOT NULL,
    classes TEXT NOT NULL,
    fees TEXT NOT NULL,
    facilities TEXT DEFAULT '',
    methodology TEXT DEFAULT '',
    contact TEXT DEFAULT '',
    rating REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recommendation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES school(id) ON DELETE CASCADE,
    match_score REAL DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS admission (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES school(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'Applied',
    application_date TEXT DEFAULT '',
    interview_date TEXT DEFAULT '',
    documents TEXT DEFAULT '',
    fee TEXT DEFAULT '',
    contact TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(child_id, school_id)
);

CREATE TABLE IF NOT EXISTS admission_step (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admission_id INTEGER NOT NULL REFERENCES admission(id) ON DELETE CASCADE,
    step_key TEXT NOT NULL,
    step_name TEXT NOT NULL,
    step_order INTEGER NOT NULL,
    status TEXT DEFAULT 'pending',
    step_data TEXT DEFAULT '',
    completed_at TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS teacher (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    phone TEXT NOT NULL,
    city TEXT NOT NULL,
    qualification TEXT DEFAULT '',
    experience TEXT DEFAULT '',
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_child (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teacher(id) ON DELETE CASCADE,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_observation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teacher(id) ON DELETE CASCADE,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,
    rating INTEGER DEFAULT 3,
    remarks TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS teacher_recommendation (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    teacher_id INTEGER NOT NULL REFERENCES teacher(id) ON DELETE CASCADE,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    school_id INTEGER NOT NULL REFERENCES school(id) ON DELETE CASCADE,
    note TEXT DEFAULT '',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(teacher_id, child_id, school_id)
);

CREATE TABLE IF NOT EXISTS admin (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS certificate (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    child_id INTEGER NOT NULL REFERENCES child(id) ON DELETE CASCADE,
    assessment_id INTEGER NOT NULL REFERENCES assessment(id) ON DELETE CASCADE,
    certificate_code TEXT NOT NULL UNIQUE,
    issued_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(child_id, assessment_id)
);
"""

SCHOOLS = [
    # ------- PUNE -------
    (
        "Sunrise International School", "Pune", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹1,20,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Activity-based learning", "020-2456-7890", 4.5,
    ),
    (
        "Vidyadeep English Medium School", "Pune", "State Board",
        "Nursery, LKG, UKG, Primary", "₹45,000 / year",
        "Playground, Library",
        "Activity + Traditional", "020-2456-1122", 4.2,
    ),
    (
        "Shree Gurukul Academy", "Pune", "State Board",
        "LKG, UKG, Primary", "₹35,000 / year",
        "Playground, Arts Room",
        "Traditional teaching", "020-2456-3344", 4.0,
    ),
    (
        "Little Wonders Kidz School", "Pune", "CBSE",
        "Nursery, LKG, UKG", "₹60,000 / year",
        "Play Area, Library, Music Room",
        "Play-based learning", "020-2456-5566", 4.3,
    ),
    (
        "Pune Model School", "Pune", "State Board",
        "Nursery, LKG, UKG, Primary", "₹28,000 / year",
        "Playground, Library",
        "Traditional teaching", "020-2456-7788", 3.9,
    ),
    (
        "The Bishop's School", "Pune", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹85,000 / year",
        "Playground, Library, Computer Lab, Music Room",
        "Activity + Traditional", "020-2567-8899", 4.5,
    ),
    (
        "Podar International School", "Pune", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹95,000 / year",
        "Smart Classrooms, Playground, Library, Transport",
        "International teaching", "020-2567-2233", 4.4,
    ),
    (
        "Indira National School", "Pune", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹70,000 / year",
        "Playground, Library, Computer Lab, Swimming Pool",
        "Activity-based learning", "020-2567-4455", 4.3,
    ),
    (
        "Riverdale High School", "Pune", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹78,000 / year",
        "Playground, Library, Arts Room, Transport",
        "Activity-based learning", "020-2567-6677", 4.4,
    ),
    (
        "City Pride School", "Pune", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹62,000 / year",
        "Play Area, Library, Computer Lab",
        "Modern teaching", "020-2567-8890", 4.1,
    ),

    # ------- PIMPRI-CHINCHWAD -------
    (
        "Army Public School", "Pimpri-Chinchwad", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹55,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Disciplined teaching", "020-2760-1122", 4.2,
    ),
    (
        "Gurukul International School", "Pimpri-Chinchwad", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹65,000 / year",
        "Playground, Library, Smart Classrooms",
        "Modern teaching", "020-2760-3344", 4.3,
    ),

    # ------- MUMBAI -------
    (
        "St. Xavier's High School", "Mumbai", "ICSE",
        "LKG, UKG, Primary", "₹90,000 / year",
        "Playground, Swimming Pool, Library, Computer Lab",
        "Activity + Traditional", "022-2530-4455", 4.6,
    ),
    (
        "Cathedral & John Connon School", "Mumbai", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹2,40,000 / year",
        "Playground, Library, Science Lab, Swimming Pool",
        "International teaching", "022-2204-8899", 4.7,
    ),
    (
        "Jamnabai Narsee School", "Mumbai", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹1,80,000 / year",
        "Playground, Library, Computer Lab, Auditorium",
        "Activity-based learning", "022-2629-1122", 4.6,
    ),
    (
        "Campion School", "Mumbai", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹1,50,000 / year",
        "Playground, Library, Science Lab, Music Room",
        "Traditional + Activity", "022-2352-3344", 4.5,
    ),
    (
        "Ryan International School", "Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹1,00,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "022-2520-5566", 4.4,
    ),
    (
        "Podar International School", "Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹1,30,000 / year",
        "Smart Classrooms, Playground, Library, Transport",
        "International teaching", "022-2520-6677", 4.3,
    ),
    (
        "VIBGYOR High School", "Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹1,40,000 / year",
        "Playground, Library, Arts Room, Computer Lab",
        "International teaching", "022-2520-7788", 4.4,
    ),
    (
        "Green Lawns High School", "Mumbai", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹90,000 / year",
        "Playground, Library, Computer Lab",
        "Activity-based learning", "022-2520-8899", 4.0,
    ),
    (
        "Bombay Scottish School", "Mumbai", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹1,60,000 / year",
        "Playground, Library, Science Lab, Music Room",
        "Activity + Traditional", "022-2634-9900", 4.5,
    ),

    # ------- NAVI MUMBAI -------
    (
        "DAV Public School", "Navi Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹75,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "022-2754-1122", 4.3,
    ),
    (
        "Orchids International School", "Navi Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹85,000 / year",
        "Smart Classrooms, Playground, Library",
        "International teaching", "022-2754-3344", 4.3,
    ),
    (
        "Nahar International School", "Navi Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹1,20,000 / year",
        "Playground, Library, Computer Lab, Swimming Pool",
        "International teaching", "022-2754-5566", 4.5,
    ),
    (
        "Apeejay School", "Navi Mumbai", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹80,000 / year",
        "Playground, Library, Science Lab, Transport",
        "Modern teaching", "022-2754-7788", 4.2,
    ),

    # ------- THANE -------
    (
        "St. Joseph's High School", "Thane", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹95,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Activity + Traditional", "022-2534-1122", 4.5,
    ),
    (
        "Holy Cross English High School", "Thane", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹65,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "022-2534-3344", 4.1,
    ),
    (
        "Changu Kana Thakur School", "Thane", "State Board",
        "Nursery, LKG, UKG, Primary", "₹40,000 / year",
        "Playground, Library, Arts Room",
        "Traditional teaching", "022-2534-5566", 4.0,
    ),
    (
        "Pawar Public School", "Thane", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹88,000 / year",
        "Playground, Library, Computer Lab, Smart Classrooms",
        "International teaching", "022-2534-7788", 4.3,
    ),

    # ------- NASHIK -------
    (
        "Holy Cross Convent School", "Nashik", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹80,000 / year",
        "Playground, Library, Computer Lab, Science Lab",
        "Activity-based learning", "0253-277-8899", 4.4,
    ),
    (
        "Nav Jagruti Public School", "Nashik", "State Board",
        "LKG, UKG, Primary", "₹30,000 / year",
        "Playground, Library",
        "Traditional teaching", "0253-277-1122", 4.1,
    ),
    (
        "Fravashi International Academy", "Nashik", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹95,000 / year",
        "Playground, Library, Computer Lab, Swimming Pool",
        "International teaching", "0253-277-3344", 4.5,
    ),
    (
        "Horizon Academy", "Nashik", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹70,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "0253-277-5566", 4.2,
    ),
    (
        "Don Bosco School", "Nashik", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹75,000 / year",
        "Playground, Library, Science Lab, Music Room",
        "Activity + Traditional", "0253-277-7788", 4.3,
    ),

    # ------- NAGPUR -------
    (
        "Centre Point School", "Nagpur", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹80,000 / year",
        "Playground, Library, Computer Lab, Swimming Pool",
        "International teaching", "0712-256-1122", 4.5,
    ),
    (
        "Somalwar High School", "Nagpur", "State Board",
        "Nursery, LKG, UKG, Primary", "₹35,000 / year",
        "Playground, Library",
        "Traditional teaching", "0712-256-3344", 4.2,
    ),
    (
        "Bharatiya Vidya Bhavan", "Nagpur", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹68,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "0712-256-5566", 4.3,
    ),
    (
        "St. Francis De Sales School", "Nagpur", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹72,000 / year",
        "Playground, Library, Science Lab",
        "Activity + Traditional", "0712-256-7788", 4.4,
    ),

    # ------- AURANGABAD -------
    (
        "MGM International School", "Aurangabad", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹55,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "0240-233-1122", 4.2,
    ),
    (
        "Delhi Public School", "Aurangabad", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹65,000 / year",
        "Playground, Library, Smart Classrooms, Transport",
        "International teaching", "0240-233-3344", 4.3,
    ),
    (
        "St. Francis High School", "Aurangabad", "State Board",
        "Nursery, LKG, UKG, Primary", "₹30,000 / year",
        "Playground, Library",
        "Traditional teaching", "0240-233-5566", 4.0,
    ),

    # ------- SOLAPUR -------
    (
        "Sanjay Ghodawat International School", "Solapur", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹60,000 / year",
        "Playground, Library, Computer Lab, Swimming Pool",
        "International teaching", "0217-230-1122", 4.4,
    ),
    (
        "KES English Medium School", "Solapur", "State Board",
        "Nursery, LKG, UKG, Primary", "₹30,000 / year",
        "Playground, Library",
        "Traditional teaching", "0217-230-3344", 4.1,
    ),

    # ------- KOLHAPUR -------
    (
        "Bal Vikas Mandal School", "Kolhapur", "State Board",
        "Nursery, LKG, UKG, Primary", "₹28,000 / year",
        "Playground, Library",
        "Traditional teaching", "0231-254-1122", 4.0,
    ),
    (
        "Army Public School", "Kolhapur", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹58,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Disciplined teaching", "0231-254-3344", 4.2,
    ),

    # ------- AMRAVATI -------
    (
        "Mount Carmel School", "Amravati", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹45,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "0721-266-1122", 4.2,
    ),
    (
        "Sri Ram Krishna Academy", "Amravati", "State Board",
        "Nursery, LKG, UKG, Primary", "₹32,000 / year",
        "Playground, Library",
        "Traditional teaching", "0721-266-3344", 4.0,
    ),

    # ------- NANDED -------
    (
        "Nanded City Public School", "Nanded", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹35,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "02462-222-1122", 4.1,
    ),
    (
        "St. Mary's High School", "Nanded", "State Board",
        "Nursery, LKG, UKG, Primary", "₹25,000 / year",
        "Playground, Library",
        "Traditional teaching", "02462-222-3344", 3.9,
    ),

    # ------- JALGAON -------
    (
        "Billabong High International School", "Jalgaon", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹65,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "International teaching", "0257-231-1122", 4.3,
    ),
    (
        "Little Flower English School", "Jalgaon", "State Board",
        "Nursery, LKG, UKG, Primary", "₹26,000 / year",
        "Playground, Library",
        "Traditional teaching", "0257-231-3344", 3.8,
    ),

    # ------- AHMEDNAGAR -------
    (
        "St. Lawrence High School", "Ahmednagar", "ICSE",
        "Nursery, LKG, UKG, Primary", "₹50,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "0241-233-1122", 4.2,
    ),
    (
        "Meridian School", "Ahmednagar", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹55,000 / year",
        "Playground, Library, Smart Classrooms",
        "Modern teaching", "0241-233-3344", 4.1,
    ),

    # ------- SANGLI -------
    (
        "St. Paul High School", "Sangli", "State Board",
        "Nursery, LKG, UKG, Primary", "₹28,000 / year",
        "Playground, Library",
        "Traditional teaching", "0233-254-1122", 4.0,
    ),
    (
        "Nutan Vidya Mandir", "Sangli", "State Board",
        "Nursery, LKG, UKG, Primary", "₹24,000 / year",
        "Playground, Library",
        "Traditional teaching", "0233-254-3344", 3.8,
    ),

    # ------- AKOLA -------
    (
        "Aryan Global Academy", "Akola", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹40,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "0724-243-1122", 4.1,
    ),
    (
        "Sunrise Public School", "Akola", "State Board",
        "Nursery, LKG, UKG, Primary", "₹22,000 / year",
        "Playground, Library",
        "Traditional teaching", "0724-243-3344", 3.7,
    ),

    # ------- LATUR -------
    (
        "Best English Medium School", "Latur", "State Board",
        "Nursery, LKG, UKG, Primary", "₹30,000 / year",
        "Playground, Library",
        "Traditional teaching", "02382-242-1122", 4.0,
    ),
    (
        "Mahatma Gandhi International School", "Latur", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹48,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "02382-242-3344", 4.2,
    ),

    # ------- DHULE -------
    (
        "KNP English Medium School", "Dhule", "State Board",
        "Nursery, LKG, UKG, Primary", "₹26,000 / year",
        "Playground, Library",
        "Traditional teaching", "02562-254-1122", 3.8,
    ),
    (
        "Rajashree Shahu English School", "Dhule", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹44,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "02562-254-3344", 4.1,
    ),

    # ------- SATARA -------
    (
        "Rayat Shikshan Sanstha School", "Satara", "State Board",
        "Nursery, LKG, UKG, Primary", "₹22,000 / year",
        "Playground, Library",
        "Traditional teaching", "02162-233-1122", 3.9,
    ),
    (
        "Podar International School", "Satara", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹58,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "International teaching", "02162-233-3344", 4.3,
    ),

    # ------- RATNAGIRI -------
    (
        "Sanskar English Medium School", "Ratnagiri", "State Board",
        "Nursery, LKG, UKG, Primary", "₹30,000 / year",
        "Playground, Library, Computer Lab",
        "Modern teaching", "02352-233-1122", 4.0,
    ),

    # ------- CHANDRAPUR -------
    (
        "Delhi Public School", "Chandrapur", "CBSE",
        "Nursery, LKG, UKG, Primary", "₹52,000 / year",
        "Playground, Library, Computer Lab, Transport",
        "Modern teaching", "07172-254-1122", 4.2,
    ),

    # ------- YAVATMAL -------
    (
        "Sarvodaya Public School", "Yavatmal", "State Board",
        "Nursery, LKG, UKG, Primary", "₹24,000 / year",
        "Playground, Library",
        "Traditional teaching", "07232-233-1122", 3.8,
    ),
]


def get_db():
    if "db" not in g:
        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    migrate(conn)
    seed_schools(conn)
    seed_admin(conn)
    conn.commit()
    conn.close()


def migrate(conn):
    cols = [row[1] for row in conn.execute("PRAGMA table_info(parent)").fetchall()]
    if "username" not in cols:
        conn.execute("ALTER TABLE parent ADD COLUMN username TEXT DEFAULT ''")
        count = conn.execute("SELECT COUNT(*) FROM parent").fetchone()[0]
        if count == 0:
            conn.execute(
                "CREATE UNIQUE INDEX idx_parent_username ON parent(username)"
            )

    school_cols = [
        row[1] for row in conn.execute("PRAGMA table_info(school)").fetchall()
    ]
    if "username" not in school_cols:
        conn.execute("ALTER TABLE school ADD COLUMN username TEXT DEFAULT ''")
    if "password_hash" not in school_cols:
        conn.execute("ALTER TABLE school ADD COLUMN password_hash TEXT DEFAULT ''")
    if "email" not in school_cols:
        conn.execute("ALTER TABLE school ADD COLUMN email TEXT DEFAULT ''")
    if "phone" not in school_cols:
        conn.execute("ALTER TABLE school ADD COLUMN phone TEXT DEFAULT ''")

    schools = conn.execute("SELECT * FROM school").fetchall()
    for school in schools:
        if school["username"] and school["password_hash"]:
            continue
        base = re.sub(r"[^a-z0-9]", "", (school["name"] or "").lower())
        if not base:
            base = "school"
        username = f"{base}_{school['id']}"
        email = f"{username}@school.edumentor.edu"
        conn.execute(
            "UPDATE school SET username=?, email=?, password_hash=? WHERE id=?",
            (username, email, generate_password_hash("school@123"),
             school["id"]),
        )

    assessment_cols = [
        row[1] for row in conn.execute("PRAGMA table_info(assessment)").fetchall()
    ]
    if "total_questions" not in assessment_cols:
        conn.execute("ALTER TABLE assessment ADD COLUMN total_questions INTEGER DEFAULT 16")

    skill_cols = [
        row[1] for row in conn.execute("PRAGMA table_info(skill_score)").fetchall()
    ]
    if "asked" not in skill_cols:
        conn.execute("ALTER TABLE skill_score ADD COLUMN asked INTEGER DEFAULT 2")


def seed_admin(conn):
    from werkzeug.security import generate_password_hash

    admin = conn.execute(
        "SELECT id FROM admin WHERE username = 'admin'"
    ).fetchone()
    if admin is None:
        conn.execute(
            "INSERT INTO admin (name, username, email, password_hash) "
            "VALUES (?, ?, ?, ?)",
            (
                "EduMentor Admin",
                "admin",
                "admin@edumentor.com",
                generate_password_hash("admin123"),
            ),
        )


def seed_schools(conn):
    existing = {
        row[0].strip().lower()
        for row in conn.execute("SELECT name FROM school").fetchall()
    }
    to_insert = [
        school for school in SCHOOLS
        if school[0].strip().lower() not in existing
    ]
    if not to_insert:
        return
    conn.executemany(
        """
        INSERT INTO school
            (name, location, syllabus, classes, fees, facilities,
             methodology, contact, rating)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        to_insert,
    )