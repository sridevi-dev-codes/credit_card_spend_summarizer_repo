# def main():
#     print("Hello from credit-card-spend-summarizer!")


# if __name__ == "__main__":
#     main()

# main.py

# from fastapi import FastAPI
# from src.api.v1.routes.upload import router as upload_router

# app = FastAPI()

# app.include_router(upload_router)
# ____________________________

# from fastapi import FastAPI

# from src.api.v1.routes.upload import router as upload_router
# from src.api.v1.routes.chat import router as chat_router

# app = FastAPI()

# app.include_router(upload_router)
# app.include_router(chat_router)


from fastapi import FastAPI

from src.api.v1.routes.upload import router as upload_router
from src.api.v1.routes.query import router as query_router

app = FastAPI()

app.include_router(upload_router, prefix="/api/v1")
app.include_router(query_router, prefix="/api/v1")