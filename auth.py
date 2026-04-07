from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from database import get_db
import models, schemas
from auth_utils import hash_password, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()


def user_to_response(user: models.User) -> schemas.AuthUserResponse:
    return schemas.AuthUserResponse(
        id=str(user.id),
        email=user.email,
        displayName=user.display_name,
    )


@router.post("/register", response_model=schemas.AuthUserResponse, status_code=201)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"type": "https://httpstatuses.com/409", "title": "Conflict", "status": 409,
                    "errors": {"email": ["Email already in use."]}},
        )

    user = models.User(
        email=body.email,
        password_hash=hash_password(body.password),
        display_name=body.displayName,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_to_response(user)


@router.post("/login", response_model=schemas.LoginResponse, status_code=200)
def login(body: schemas.LoginRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == body.email).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"type": "https://httpstatuses.com/401", "title": "Unauthorized",
                    "status": 401, "errors": {"credentials": ["Invalid email or password."]}},
        )

    token = create_access_token(str(user.id))
    return schemas.LoginResponse(
        accessToken=token,
        tokenType="Bearer",
        expiresInSeconds=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_to_response(user),
    )
