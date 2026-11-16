import urllib.request, urllib.parse, http.cookiejar, re
base="http://127.0.0.1:5010"
jar=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
def get(p):
    r=op.open(base+p); return r.getcode(), r.read().decode("utf-8","replace"), r.geturl()
def post(p,d):
    req=urllib.request.Request(base+p,data=urllib.parse.urlencode(d).encode())
    r=op.open(req); return r.getcode(), r.read().decode("utf-8","replace"), r.geturl()
for ident in ("sakshisarnaik","sakshisarnaik@gmail.com"):
    code,body,url=post("/login",{"email":ident,"password":"test1234","role":"parent"})
    print(ident, code, url, re.findall(r'flash flash-(\w+)">(.*?)</div>',body,re.S)[:2])
for p in ["/parent/dashboard","/parent/child","/parent/assessment","/parent/assessment/questions","/parent/results","/parent/certificate","/parent/observations","/parent/recommendations","/parent/admissions","/parent/profile"]:
    code,body,url=get(p)
    print(p, code, url.replace(base,''), len(body))
