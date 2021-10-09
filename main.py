from fastapi import FastAPI, Request, HTTPException, status, Depends
from tortoise.contrib.fastapi import register_tortoise
from models import *
from email_helper import *
from database import init_db

# authentication
from authentication import (get_hashed_password, verify_token, token_generator)
from fastapi.security import (OAuth2PasswordBearer, OAuth2PasswordRequestForm)

#signals
from tortoise.signals import post_save
from typing import List, Optional, Type
from tortoise import BaseDBAsyncClient

# response classes
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

# image upload
from fastapi import File, UploadFile
import secrets
from fastapi.staticfiles import StaticFiles
from PIL import Image

app = FastAPI()


@app.on_event("startup")
async def startup_event():
    init_db(app)


oauth2_schema = OAuth2PasswordBearer(tokenUrl='token')

# static file setup config
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.post('/token')
async def generate_token(request_form: OAuth2PasswordRequestForm=Depends()):
    token = await token_generator(request_form.username, request_form.password)
    return {
        "access_token": token,
        "token_type": "bearer"
    }


async def get_current_user(token:str=Depends(oauth2_schema)):
    try:
        payload = jwt.decode(token, config_credentials['SECRET_KEY'], algorithms="HS256")
        user = await User.get(id=payload.get("id"))

    except jwt.exceptions.DecodeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid token, please request a new one", headers={"WWW-Authenticate": "Bearer"})

    return await user


@app.post('/user/me')
async def user_login(request: Request, user: user_pydanticIn=Depends(get_current_user)):
    business = await Business.get(owner=user)
    logo = business.logo
    logo_path = f"http://{request.client.host}:8000/static/images/{logo}"

    return {
        "status": "ok",
        "data": {
            "username": user.username,
            "email": user.email,
            "verified": user.is_verified,
            "joined_date": user.join_date.strftime('%m-%d-%Y'),
            "logo": logo_path
        }
    }


@post_save(User)
async def create_business(
    sender: "Type[User]",
    instance: User,
    created: bool,
    using_db: "Optional[BaseDBAsyncClient]",
    update_fields: List[str]
) -> None:
    if created:
        print('create business')
        business_obj = await Business.create(
            business_name=instance.username,
            owner=instance
        )
        await business_pydantic.from_tortoise_orm(business_obj)


@app.post('/registration')
async def user_registration(user: user_pydanticIn, request: Request):
    user_info = user.dict(exclude_unset=True)
    user_info['password'] = get_hashed_password(user_info['password'])
    user_obj = await User.create(**user_info)
    new_user = await user_pydantic.from_tortoise_orm(user_obj)

    client_host = request.client.host
    await send_email([new_user.email], user_obj, client_host)

    return {
        "status": "ok",
        "data": f"Hello {new_user.username}, thanks for choosing "
                f"our services. Please check your email inbox and click on the link to confirm your email"
    }


templates = Jinja2Templates(directory="templates")



@app.get('/email-verify', response_class=HTMLResponse)
async def email_verification(request: Request, token: str):
    user = await verify_token(token)

    if user and not user.is_verified:
        user.is_verified = True
        await user.save()
        return templates.TemplateResponse("verification.html",
                                          {"request": request, "username": user.username})

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid username or password",
                            headers={"WWW-Authenticate": "Bearer"})

@app.get('/')
def index():
    return {"message": "Hello World"}


@app.post('/uploadfile/profile')
async def create_upload_file(
request: Request, file: UploadFile=File(...), user: user_pydantic=Depends(get_current_user)):
    FILEPATH = './static/images/'
    filename = file.filename
    extension = filename.split('.')[1]

    if extension not in ['png', 'jpg']:
        return {"status": "error", "detail": "File extension not allowed"}

    # /static/images/image.jpg
    token_name = secrets.token_hex(10) + '.' + extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()

    with open(generated_name, "wb") as file:
        file.write(file_content)

    # PILLOW
    img = Image.open(generated_name)
    img = img.resize(size=(200, 200))
    img.save(generated_name)

    file.close()

    business = await Business.get(owner=user)
    owner = await business.owner

    if owner == user:
        business.logo = token_name
        await business.save()
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated to perform this action",
                            headers={"WWW-Authenticate": "Bearer"})

    file_url = f"http://{request.client.host}:8000{generated_name[1:]}"
    return {"status": "ok", "filename": file_url}


@app.post('/uploadfile/product/{id}')
async def create_upload_file(request: Request, id: int, file: UploadFile=File(...), user: user_pydantic=Depends(get_current_user)):
    FILEPATH = './static/images/'
    filename = file.filename
    extension = filename.split('.')[1]

    if extension not in ['png', 'jpg']:
        return {"status": "error", "detail": "File extension not allowed"}

    # /static/images/image.jpg
    token_name = secrets.token_hex(10) + '.' + extension
    generated_name = FILEPATH + token_name
    file_content = await file.read()

    with open(generated_name, "wb") as file:
        file.write(file_content)

    # PILLOW
    img = Image.open(generated_name)
    img = img.resize(size=(200, 200))
    img.save(generated_name)

    file.close()

    product = await Product.get(id=id)
    business = await product.business_fields
    owner = await business.owner

    if owner == user:
        product.product_image = token_name
        await product.save()
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated to perform this action",
                            headers={"WWW-Authenticate": "Bearer"})

    file_url = f"http://{request.client.host}:8000{generated_name[1:]}"
    return {"status": "ok", "filename": file_url}


# CRUD functionality
@app.post('/products')
async def add_new_product(product: product_pydanticIn, user: user_pydantic=Depends(get_current_user)):
    product = product.dict(exclude_unset=True)

    # avoid divide by 0
    if product['original_price'] > 0:
        product['percentage_discount'] = ((product['original_price'] - product['new_price'])/product['original_price'])*100
        business = await Business.get(owner=user)

        product_obj = await Product.create(**product, business_fields=business)
        product_obj = await product_pydantic.from_tortoise_orm(product_obj)

        return {"status": "ok", "data": product_obj}
    else:
        return {"status": "error"}


@app.get('/product')
async def get_product():
    response = await product_pydantic.from_queryset(Product.all())
    return {"status": "ok", "data": response}


@app.get('/product/{id}')
async def get_product(id: int):
    product = await Product.get(id=id)
    business = await product.business_fields
    owner = await business.owner
    response = await product_pydantic.from_queryset_single(Product.get(id=id))

    return {
        "status": "ok",
        "data": {
            "product_details": response,
            "business_details": {
                "name": business.business_name,
                "logo": business.city,
                "city": business.region,
                "region": business.business_description,
                "business_description": business.logo,
                "owner_id": owner.id,
                "email": owner.email,
                "join_date": owner.join_date.strftime("%b %d %Y")
            }
        }
    }


@app.delete("/products/{id}")
async def delete_product(id: int, user: user_pydantic=Depends(get_current_user)):
    product = await Product.get(id=id)
    business = await product.business_fields
    owner = await business.owner

    if user == owner:
        product.delete()
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated to perform this action",
                            headers={"WWW-Authenticate": "Bearer"})

    return {"status": "ok"}


@app.put("/product/{id}")
async def update_product(id: int, update_info: product_pydanticIn, user: user_pydantic=Depends(get_current_user)):
    product = await Product.get(id=id)
    business = await product.business_fields
    owner = await business.owner

    update_info = update_info.dict(exclude_unset=True)
    update_info['date_published'] = datetime.utcnow()
    if user == owner and update_info['original_price'] > 0:
        update_info['percentage_discount'] = ((update_info['original_price'] - update_info['new_price']) / update_info['original_price'])*100
        await product.update_from_dict(update_info)
        await product.save()
        response = await product_pydantic.from_tortoise_orm(product)

        return {
            "status": "ok",
            "data": response
        }
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated to perform this action or invalid user input",
                            headers={"WWW-Authenticate": "Bearer"})


@app.put('/business/{id}')
async def update_business(id: int, update_business: business_pydanticIn
                          , user: user_pydantic=Depends(get_current_user)):
    update_business = update_business.dict()

    business = await Business.get(id=id)
    business_owner = await business.owner

    if business_owner == user:
        await business.update_from_dict(update_business)
        await business.save()
        response = await business_pydantic.from_tortoise_orm(business)

        return {
            "status": "ok",
            "data": response
        }
    else:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated to perform this action",
                            headers={"WWW-Authenticate": "Bearer"})



