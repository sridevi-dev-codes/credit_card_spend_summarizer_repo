
from fastapi import APIRouter
from pydantic import BaseModel
from src.api.v1.services.query_service import query_documents

router = APIRouter()


class QueryRequest(BaseModel):
    query: str
    session_id: str


@router.post("/query")
def query(req: QueryRequest):
    try:
        return query_documents(req.query, req.session_id)
    except Exception as e:
        print("[API ERROR]", e)
        return {
            "answer": "Internal server error",
            "route": "error"
        }


# from fastapi import APIRouter, HTTPException
# from pydantic import BaseModel

# from src.api.v1.services.query_service import query_documents

# router = APIRouter()


# class QueryRequest(BaseModel):
#     query: str
#     session_id: str


# @router.post("/query")
# def query(req: QueryRequest):
#     try:
#         result = query_documents(req.query, req.session_id)
#         return result

#     except Exception as e:
#         # log if needed
#         raise HTTPException(
#             status_code=500,
#             detail=f"Query pipeline failed: {str(e)}"
#         )


# from fastapi import APIRouter, HTTPException

# from src.api.v1.services.query_service import query_documents
# from src.api.v1.schema.query_schema import QueryRequest, QueryResponse

# router = APIRouter()

# @router.post("/query", response_model=QueryResponse)
# def query_endpoint(request: QueryRequest):
#     try:
#         response = query_documents(
#             query=request.query,
#             session_id=request.session_id
#         )
#         return response

#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=str(e)
#         )