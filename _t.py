import app as application
c = application.app.test_client()
def try_login(role, ident, pw):
    r = c.post("/login", data={"email": ident, "password": pw, "role": role}, follow_redirects=True)
    body = r.get_data(as_text=True)
    ok = "Welcome back" in body
    msg = ""
    if "flash-danger" in body:
        import re
        m = re.findall(r'flash flash-danger">(.*?)</div>', body, re.S)
        msg = " | ".join(x.strip() for x in m)
    print(f"{role:8} {ident:40} -> {r.status_code} login_ok={ok} {msg[:160]}")

try_login("admin", "admin", "admin123")
try_login("school", "sunriseinternationalschool_1", "school@123")
try_login("school", "sunriseinternationalschool_1@school.edumentor.edu", "school@123")
try_login("teacher", "sneha", "anything")
try_login("parent", "shivanjali", "anything")
