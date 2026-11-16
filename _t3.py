import re, sqlite3
import app as application
c = application.app.test_client()

def show(r):
    body = r.get_data(as_text=True)
    msgs = re.findall(r'class="flash flash-(\w+)">(.*?)</div>', body, re.S)
    return r.status_code, [f"{k}:{v.strip()[:120]}" for k,v in msgs]

# 1) login as teacher with known password
r = c.post("/login", data={"email":"sneha","password":"admin123","role":"teacher"}, follow_redirects=True)
print("teacher sneha ->", show(r), "Welcome back" in r.get_data(as_text=True))

# 2) register a brand new parent then login
r = c.post("/register", data={
    "role":"parent","full_name":"Test Parent","username":"testparent1",
    "email":"testparent1@example.com","phone":"9876543210","city":"Pune",
    "password":"test1234","confirm_password":"test1234"}, follow_redirects=True)
print("register parent ->", show(r))

r = c.post("/login", data={"email":"testparent1","password":"test1234","role":"parent"}, follow_redirects=True)
print("login new parent ->", show(r), "Welcome back" in r.get_data(as_text=True))

# 3) register a new school then login
r = c.post("/register", data={
    "role":"school","full_name":"Test School","username":"testschool1",
    "email":"testschool1@example.com","phone":"9876543211","city":"Pune",
    "password":"test1234","confirm_password":"test1234"}, follow_redirects=True)
print("register school ->", show(r))

r = c.post("/login", data={"email":"testschool1","password":"test1234","role":"school"}, follow_redirects=True)
print("login new school ->", show(r), "Welcome back" in r.get_data(as_text=True))
