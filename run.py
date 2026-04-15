import os
import uvicorn
from app.database import init_db

if __name__ == "__main__":
    os.makedirs("data/exports", exist_ok=True)
    init_db()
    print("Pipefire körs på http://localhost:8000")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
