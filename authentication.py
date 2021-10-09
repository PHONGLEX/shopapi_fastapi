import jwt
from fastapi import HTTPException, status

from passlib.context import CryptContext
from dotenv import dotenv_values
from models import User


config_credential = dotenv_values('.env')
pwd_context = CryptContext(schemes=['bcrypt'], deprecated='auto')


def get_hashed_password(password):
    return pwd_context.hash(password)


async def verify_token(token: str):
    try:
        payload = jwt.decode(token, config_credential['SECRET_KEY'], algorithms="HS256")
        user = await User.get(id=payload['id'])

    except jwt.exceptions.DecodeError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})

    return user


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


async def authenticate_user(username: str, password: str):
    user = await User.get(username=username)

    if user and verify_password(password, user.password):
        return user

    return False


async def token_generator(username: str, password: str):
    user = await authenticate_user(username, password)
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials, please try again", headers={"WWW-Authenticate": "Bearer"})

    token_data = {
        "id": user.id,
        "username": user.username,
    }

    token = jwt.encode(token_data, config_credential['SECRET_KEY'], algorithm="HS256")

    return token