import sqlite3
c = sqlite3.connect("edumentor.db")
c.execute("DELETE FROM parent WHERE username LIKE 'testparent%'")
c.execute("DELETE FROM school WHERE username LIKE 'testschool%'")
c.commit()
print("cleaned:", c.execute("SELECT COUNT(*) FROM parent").fetchone()[0], "parents,", c.execute("SELECT COUNT(*) FROM school").fetchone()[0], "schools")
