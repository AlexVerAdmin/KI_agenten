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

@app.post("/execute")
async def execute_command(command: str, x_token: str = Header(None)):
    """Выполнение системной команды локально на ноде воркера."""
    verify_token(x_token)
    import subprocess
    try:
        # Простая проверка на опасные команды
        forbidden = ["rm -rf /", "mkfs", "dd if="]
        if any(f in command for f in forbidden):
            return {"status": "error", "output": "Forbidden command"}
            
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout if result.stdout else result.stderr
        return {"status": "success", "output": output}
    except Exception as e:
        return {"status": "error", "output": str(e)}

@app.get("/health")
async def health():
    return {"status": "OK", "worker": "HomeLab"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
