from fastapi import FastAPI, HTTPException, Header
import os
import uvicorn
from core.memory import vector_db_search_tool, index_knowledge_base
from config import config

app = FastAPI(title="Personal RAG Worker (Home Lab)")

# Простейшая защита эндпоинта
API_SECRET = os.getenv("API_SECRET", "change_me_in_env")

def verify_token(x_token: str = Header(None)):
    if x_token != API_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid Secret Token")

@app.post("/search")
async def search_docs(query: str, x_token: str = Header(None)):
    verify_token(x_token)
    results = vector_db_search_tool(query)
    return {"results": results}

@app.post("/reindex")
async def reindex(x_token: str = Header(None)):
    verify_token(x_token)
    index_knowledge_base()
    return {"status": "Indexing completed"}

@app.get("/health")
async def health():
    return {"status": "OK", "worker": "HomeLab"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
