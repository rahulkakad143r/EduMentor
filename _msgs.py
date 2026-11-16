import sqlite3, os, json
p = os.path.expanduser(r"~\.local\share\opencode\opencode.db")
c = sqlite3.connect(p); c.row_factory=sqlite3.Row
sid="ses_e898500d0ffez2kOWkqJYIvmyc"
print("session_message", c.execute("SELECT COUNT(*) FROM session_message WHERE session_id=?",(sid,)).fetchone()[0])
print("message", c.execute("SELECT COUNT(*) FROM message WHERE session_id=?",(sid,)).fetchone()[0])
for m in c.execute("SELECT id,data FROM message WHERE session_id=? ORDER BY time_created LIMIT 5",(sid,)):
    d=json.loads(m["data"]); print(d.get("role"), str(d)[:200])
