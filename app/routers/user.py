from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.authentication import get_current_user, get_password_hash, SECRET_KEY, ALGORITHM
from app.database import get_db
from app.mail import send_reset_email
from app.models import User
from app.routers.authentication import create_access_token
from app.schemas import user as user_schema
from app.schemas.user import ChangePasswordRequest, SuccessMessage, ResetPasswordRequest, ForgotPasswordRequest
from app.crud import user as crud
from app.security import hash_password, verify_password

router = APIRouter()


@router.post("/signUp", response_model=SuccessMessage)
def create_user(user: user_schema.UserCreate1, db: Session = Depends(get_db)):
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    crud.create_user1(db=db, user=user)
    return {"message": "Registration successful"}


@router.get("/{user_id}", response_model=user_schema.UserOut)
def read_user(user_id: int, db: Session = Depends(get_db)):
    db_user = crud.get_user(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return db_user


@router.post("/change-password", response_model=SuccessMessage)
def change_password(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not verify_password(data.old_password, current_user.password):
        raise HTTPException(status_code=400, detail="Old password is incorrect")

    current_user.password = hash_password(data.new_password)
    db.commit()

    return {"message": f"Password changed successfully for {current_user.role}"}

@router.post("/forgot-password")
def forgot_password(request: ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = crud.get_user_by_email(db, request.email)
    if not user:
        # To prevent attackers from knowing valid emails
        return {"msg": "If this email exists, a reset link has been sent."}

    # Create short-lived token (15 mins)
    reset_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=15)
    )

    reset_link = f"http://localhost:8080/reset-password?token={reset_token}"
    send_reset_email(user.email, reset_link)

    # TODO: Actually send this via email
    print(f"[DEBUG] Reset link: {reset_link}")

    return {"msg": "If this email exists, a reset link has been sent."}

@router.post("/reset-password")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Invalid or expired token"
    )
    try:
        payload = jwt.decode(request.token, SECRET_KEY, algorithms=[ALGORITHM])
        email = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = crud.get_user_by_email(db, email)
    if not user:
        raise credentials_exception

    # Hash and update password
    user.password = get_password_hash(request.new_password)
    db.commit()

    return {"msg": "Password reset successful"}