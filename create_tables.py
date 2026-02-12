from app.core.database import engine
from app.models.user import Base
from app.models.employees import Base

Base.metadata.drop_all(bind=engine)   # WARNING: deletes all data in tables!
Base.metadata.create_all(bind=engine)