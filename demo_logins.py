import sqlite3

from werkzeug.security import generate_password_hash

import db

DEMO_LOGINS = [
    ("admin", "admin", "admin123",
     ("EduMentor Admin", "admin", "admin@edumentor.com")),
    ("teacher", "sneha", "teacher@123",
     ("Sneha Kadam", "sneha", "snehaska12@gmail.com", "9999999999", "Pune")),
    ("parent", "shivanjali", "parent@123",
     ("Shivanjali Mattikalli", "shivanjali",
      "shivanjalichougule720@gmail.com", "9999999999", "Pune")),
]


def ensure_account(conn, table, username, password, profile):
    row = conn.execute(
        f"SELECT id FROM {table} WHERE LOWER(username) = ?", (username.lower(),)
    ).fetchone()
    password_hash = generate_password_hash(password)

    if row is not None:
        conn.execute(
            f"UPDATE {table} SET password_hash = ? WHERE id = ?",
            (password_hash, row["id"]),
        )
        return f"updated  {table:7} {username}"

    if table == "admin":
        conn.execute(
            "INSERT INTO admin (name, username, email, password_hash) "
            "VALUES (?, ?, ?, ?)",
            (*profile, password_hash),
        )
    else:
        conn.execute(
            f"INSERT INTO {table} "
            "(name, username, email, phone, city, password_hash) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (*profile, password_hash),
        )
    return f"created  {table:7} {username}"


def ensure_school(conn, username, password):
    school = conn.execute(
        "SELECT id FROM school WHERE LOWER(username) = ?", (username.lower(),)
    ).fetchone()
    if school is None:
        school = conn.execute(
            "SELECT id FROM school ORDER BY id LIMIT 1"
        ).fetchone()
    password_hash = generate_password_hash(password)
    email = f"{username}@school.edumentor.edu"
    conn.execute(
        "UPDATE school SET username = ?, email = ?, password_hash = ? "
        "WHERE id = ?",
        (username, email, password_hash, school["id"]),
    )
    return f"updated  school  {username}"


def main():
    conn = sqlite3.connect(db.DATABASE)
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    db.migrate(conn)
    db.seed_schools(conn)
    db.seed_admin(conn)

    for table, username, password, profile in DEMO_LOGINS:
        print(ensure_account(conn, table, username, password, profile))
    print(ensure_school(conn, "sunriseinternationalschool_1", "school@123"))

    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
