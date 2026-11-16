import urllib.request, urllib.parse, http.cookiejar, re

BASE = "http://127.0.0.1:5000"
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def post(path, data, follow=True):
    data = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(BASE + path, data=data)
    try:
        r = op.open(req)
        return r.getcode(), r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), path

def flashes(body):
    return [(m.group(1), m.group(2).strip()[:150]) for m in re.finditer(r'class="flash flash-(\w+)">(.*?)</div>', body, re.S)]

def login(role, ident, pw, label=""):
    code, body, url = post("/login", {"email": ident, "password": pw, "role": role})
    print(f"[{label}] {role:7} {ident:35} code={code} final={url.replace(BASE,'')} flashes={flashes(body)[:3]}")
    return code, body, url

# admin login (known good)
login("admin", "admin", "admin123", "admin")

# admin resets parent 31 credentials via admin panel
code, body, url = post("/admin/parents", {"parent_id": 31, "username": "sakshisarnaik", "email": "sakshisarnaik@gmail.com", "password": "parent123"})
print("admin reset parent ->", code, flashes(body)[:3])

# now parent login
login("parent", "sakshisarnaik", "parent123", "parent")
login("parent", "sakshisarnaik@gmail.com", "parent123", "parent-email")
login("teacher", "sneha", "admin123", "teacher")
login("school", "sunriseinternationalschool_1", "school@123", "school")
