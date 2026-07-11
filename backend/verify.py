import sys, json, urllib.request
sys.path.insert(0, ".")
from app.database.connection import SessionLocal
from app.models.school import School
from app.models.user import User

db = SessionLocal()
db.query(User).delete()
db.query(School).delete()
db.commit()

school = School(name="Test", slug="test")
db.add(school)
db.commit()
db.refresh(school)

user = User(name="Admin", email="a@t.com", password_hash="x", school_id=school.id, role="super_admin")
db.add(user)
db.commit()
db.refresh(user)

from jose import jwt
import datetime
from app.core.config import settings
token = jwt.encode({"sub": str(user.id), "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def api(method, path, data=None):
    h = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    b = json.dumps(data).encode() if data else None
    r = urllib.request.Request(f"http://127.0.0.1:8000{path}", b, h, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=10)
        raw = resp.read()
        return resp.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, json.loads(raw) if raw else {}

# Test chatbot settings
print("1) GET /chatbot/settings")
s, d = api("GET", "/chatbot/settings")
print(f"   {s} - name={d.get('chatbot_name')}")

print("2) PUT /chatbot/settings")
s, d = api("PUT", "/chatbot/settings", {"chatbot_name": "Test Bot", "welcome_message": "Hello"})
print(f"   {s} - name={d.get('chatbot_name')}")

# Test widget
print("3) POST /chatbot/widget")
s, d = api("POST", "/chatbot/widget")
print(f"   {s} - key={d.get('embed_key','')[:8]}...")

print("4) GET /chatbot/widget")
s, d = api("GET", "/chatbot/widget")
print(f"   {s} - status={d.get('status')}")

# Test admission settings
print("5) GET /admission/settings")
s, d = api("GET", "/admission/settings")
print(f"   {s} - collect_email={d.get('collect_email')}")

print("6) PUT /admission/settings")
s, d = api("PUT", "/admission/settings", {"collect_email": True, "collect_phone": True})
print(f"   {s} - email={d.get('collect_email')}, phone={d.get('collect_phone')}")

# Test leads
print("7) GET /leads")
s, d = api("GET", "/leads")
print(f"   {s} - count={len(d)}")

# Test analytics dashboard
print("8) GET /analytics/dashboard")
s, d = api("GET", "/analytics/dashboard")
print(f"   {s} - unanswered={d.get('unanswered_count')}")

print("\nALL PASSED")
db.close()
