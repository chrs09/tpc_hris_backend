from app.core.database import engine, Base


# Base.metadata.drop_all(bind=engine)  # WARNING: deletes all data!
Base.metadata.create_all(bind=engine)
