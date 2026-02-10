from app.core.database import SessionLocal
from app.models.user import User
from app.core.security import hash_password

db = SessionLocal()

users = [
    {"username": "anne","email": "anne@tytan.com", "password": "admin123", "role": "admin", "is_active": True},
    {"username": "ian","email": "ian@tytan.com", "password": "employee123", "role": "employee", "is_active": True},
]

for u in users:
    exists = db.query(User).filter(User.email == u["email"]).first()
    if not exists:
        user = User(
            username=u["username"],
            email=u["email"],
            hashed_password=hash_password(u["password"]),
            role=u["role"],
            is_active=u["is_active"]
        )
        db.add(user)

db.commit()
db.close()

print("✅ Users seeded successfully")