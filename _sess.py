import sqlite3, os, json
p = os.path.expanduser(r"~\.local\share\opencode\opencode.db")
c = sqlite3.connect(p); c.row_factory=sqlite3.Row
rows = c.execute("SELECT id,title,directory,time_created,time_updated FROM session ORDER BY time_updated DESC LIMIT 8").fetchall()
for r in rows:
    print(r["id"], r["time_updated"], r["directory"], "|", r["title"][:100])
