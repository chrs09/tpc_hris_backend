from datetime import date
from app.core.database import Base, SessionLocal
from app.models.user import User
from app.models.employees import Employee
from app.core.security import hash_password
import random

Base.metadata.create_all(bind=SessionLocal().get_bind())  # Ensure tables are created

db = SessionLocal()

# Users to create
users = [
    {"username": "anne", "email": "anne@tytan.com", "password": "admin123", "role": "admin", "is_active": True},
    {"username": "ian", "email": "ian@tytan.com", "password": "employee123", "role": "employee", "is_active": True},
]

# Sample first and last names to generate employees
first_names = ["John", "Jane", "Alice", "Bob", "Michael", "Sara"]
last_names = ["Doe", "Smith", "Johnson", "Brown", "Taylor", "Lee"]

# Sample positions and departments
positions = ["Engineer", "HR Specialist", "Manager", "Designer"]
departments = ["IT", "HR", "Finance", "Design"]

for u in users:
    # Check if user already exists
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
        db.commit()        # Commit so user.id exists
        db.refresh(user)   # Refresh the instance

        # If user is admin, create 3 random employees for them
        if user.role == "admin":
            for _ in range(3):
                first_name = random.choice(first_names)
                last_name = random.choice(last_names)
                employee = Employee(
                    first_name=first_name,
                    last_name=last_name,
                    email=f"{first_name.lower()}.{last_name.lower()}@tytan.com",
                    position=random.choice(positions),
                    department=random.choice(departments),
                    date_hired=date.today(),
                    is_active=1,
                    created_by_user_id=user.id  # use ID explicitly
                )
                db.add(employee)

db.commit()
db.close()

print("✅ Users and employees seeded dynamically successfully")