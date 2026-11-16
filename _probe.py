import traceback
import app as application
c = application.app.test_client()
routes = ["/parent/dashboard","/parent/child","/parent/assessment","/parent/assessment/questions","/parent/results","/parent/certificate","/parent/observations","/parent/recommendations","/parent/admissions","/parent/profile"]
for uid in (26,27,31):
    with c.session_transaction() as s:
        s["role"]="parent"; s["user_id"]=uid
    print("=== parent", uid)
    for r in routes:
        try:
            resp = c.get(r, follow_redirects=False)
            body = resp.get_data(as_text=True)
            flag = "OK" if resp.status_code in (200,302) else "FAIL"
            print(f"{flag} {resp.status_code} {r} len={len(body)}")
            if resp.status_code >= 500:
                print(body[:3000])
        except Exception as e:
            print("EXC", r, repr(e))
            traceback.print_exc()
