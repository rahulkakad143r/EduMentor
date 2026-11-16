import sqlite3, os, json
p = os.path.expanduser(r"~\.local\share\opencode\opencode.db")
c = sqlite3.connect(p); c.row_factory=sqlite3.Row
sid="ses_e898500d0ffez2kOWkqJYIvmyc"
msgs=c.execute("SELECT id,data,time_created FROM message WHERE session_id=? ORDER BY time_created",(sid,)).fetchall()
for m in msgs:
    md=json.loads(m["data"]); role=md.get("role")
    parts=c.execute("SELECT data FROM part WHERE message_id=? ORDER BY time_created",(m["id"],)).fetchall()
    texts=[]
    for pp in parts:
        pd=json.loads(pp["data"])
        t=pd.get("type")
        if t=="text": texts.append(pd.get("text",""))
        elif t=="tool": texts.append("[tool "+str(pd.get("tool"))+" "+json.dumps(pd.get("state",{}))[:300]+"]")
    if texts:
        print("\n=====",role,m["time_created"])
        print("\n".join(texts)[:5000])
