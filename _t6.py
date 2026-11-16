import sqlite3
from werkzeug.security import check_password_hash
p = r"C:\Users\Sneha Kadam\AppData\Local\Temp\opencode\edutest\edumentor.db"
c = sqlite3.connect(p); c.row_factory = sqlite3.Row
for t in ("parent","teacher","admin"):
    print("==", t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    for r in c.execute(f"SELECT id,name,username,email,password_hash FROM {t}"):
        print(" ", dict(r))
print("== school 1:", dict(c.execute("SELECT id,username,email,password_hash FROM school WHERE id=1").fetchone()))
