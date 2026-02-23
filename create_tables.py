from app.core.database import engine, Base

# import all models
from app.models.user import User
from app.models.employees import Employee
from app.models.attendance import AttendanceRecord  # or whatever your class names are

print("Tables detected:", Base.metadata.tables.keys())

Base.metadata.create_all(bind=engine)

print("Tables created successfully.")
