import sqlite3
from werkzeug.security import check_password_hash
c = sqlite3.connect("edumentor.db"); c.row_factory = sqlite3.Row
ident = "sakshisarnaik"
row = c.execute("SELECT * FROM parent WHERE LOWER(email) = ? OR LOWER(username) = ?", (ident, ident)).fetchone()
print("direct query ->", dict(row) if row else None)
if row:
    print("hash:", row["password_hash"])
    print("parent123 ->", check_password_hash(row["password_hash"], "parent123"))
row2 = c.execute("SELECT * FROM teacher WHERE LOWER(email) = ? OR LOWER(username) = ?", ("sneha","sneha")).fetchone()
print("teacher row:", dict(row2) if row2 else None)
if row2: print("admin123 ->", check_password_hash(row2["password_hash"], "admin123"))
