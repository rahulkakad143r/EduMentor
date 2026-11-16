import sqlite3
from werkzeug.security import check_password_hash
c = sqlite3.connect("edumentor.db"); c.row_factory = sqlite3.Row
common = ["admin123","school@123","teacher@123","parent@123","password","123456","password123",
          "test1234","user1234","edumentor123","EduMentor123","admin@123","school123","teacher123",
          "parent123","student123","12345678","abc12345","qwerty123","welcome1","Pune@123","sneha123"]
for t in ("parent","teacher"):
    for r in c.execute(f"SELECT id, username, email, password_hash FROM {t}"):
        found = [p for p in common if check_password_hash(r["password_hash"], p)]
        print(t, r["id"], r["username"], "->", found)
