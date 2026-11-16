import sqlite3, os
p = os.path.expanduser(r"~\.local\share\opencode\opencode.db")
c = sqlite3.connect(p); c.row_factory=sqlite3.Row
print([r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")])
for t in [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]:
    cols=[r[1] for r in c.execute(f"PRAGMA table_info({t})")]
    print(t, cols)
