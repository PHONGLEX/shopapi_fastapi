from fastapi import FastAPI
from tortoise.contrib.fastapi import register_tortoise


TORTOISE_ORM = {
    "connections": {
         "default": "postgres://postgres:postgres@localhost/ecommerceDB"
    },
    "apps": {
        "models": [
             "models", "aerich.models"
        ],
        "default_connection": "default",
    },
}


def init_db(app: FastAPI) -> None:
    register_tortoise(
        app,
        db_url="postgres://postgres:postgres@localhost/ecommerceDB",
        modules={"models": ["models"]},
        generate_schemas=True,
        add_exception_handlers=True
    )

