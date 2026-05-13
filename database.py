from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

# Set this in your .env file! 
# Example: DATABASE_URL=postgresql://postgres:yourpassword@localhost:5432/eduassist
SQLALCHEMY_DATABASE_URL = os.environ.get("DATABASE_URL") 

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()