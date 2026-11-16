import sqlite3
c = sqlite3.connect("edumentor.db"); c.row_factory = sqlite3.Row
for t in ("parent","teacher"):
    print("==", t)
    for r in c.execute(f"SELECT id,name,username,email,phone,city FROM {t}"):
        print({k: repr(r[k]) for k in r.keys()})
print("== school sample (id,username,email)")
for r in c.execute("SELECT id,username,email,location,syllabus,classes,fees FROM school WHERE id IN (1,5,60,64,65,66)"):
    print({k: repr(r[k]) for k in r.keys()})
