from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from uuid import uuid4

from app.db import engine, SessionLocal

app = FastAPI()


@app.get("/")
def read_root():
    return {"message": "Confidence Pool API is running"}


@app.get("/db-test")
def db_test():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        return {"db_response": [row[0] for row in result]}


@app.post("/users")
def create_user(email: str, display_name: str):
    db = SessionLocal()
    try:
        user_id = str(uuid4())

        db.execute(
            text("""
                insert into users (id, email, display_name)
                values (:id, :email, :display_name)
            """),
            {
                "id": user_id,
                "email": email,
                "display_name": display_name
            }
        )
        db.commit()

        return {
            "id": user_id,
            "email": email,
            "display_name": display_name
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        db.close()


@app.get("/users")
def get_users():
    db = SessionLocal()
    try:
        result = db.execute(
            text("""
                select id, email, display_name, created_at
                from users
                order by created_at desc
            """)
        )

        users = []
        for row in result:
            users.append({
                "id": str(row.id),
                "email": row.email,
                "display_name": row.display_name,
                "created_at": row.created_at.isoformat() if row.created_at else None
            })

        return users
    finally:
        db.close()