from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from app.core.database import get_db
from app.models.user import User
from app.schemas.user import UserCreate, UserLogin, UserResponse
from app.core.security import hash_password, verify_password, create_access_token
from datetime import datetime, timedelta

router = APIRouter(prefix="/auth", tags=["Auth"])


# router for getting list of user in tpc_user table
@router.get("/users", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users


# endpoint for post register request
@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    exists = db.query(User).filter(User.email == user.email).first()
    if exists:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = User(
        username=user.username.lower(),
        email=user.email,
        hashed_password=hash_password(user.password),
        role=user.role,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return {"message": "User created"}


# endpoint for post login request
@router.post("/login")
def login(credentials: UserLogin, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(func.lower(User.username) == credentials.username.lower())
        .first()
    )
    if not user or not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(
        {
            "sub": user.username, 
            "role": user.role, 
            "user_id": user.id, 
            "exp": datetime.utcnow() + timedelta(minutes=60)
        }
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": user.id,
        "username": user.username,
    }
