from sqlalchemy import Column, Integer, String
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String)
    middle_name = Column(String, nullable=True)
    last_name = Column(String)
    dob = Column(String, nullable=True)
    email = Column(String, unique=True, index=True)
    password = Column(String) # Plain text, no security
    position = Column(String)
    school_name = Column(String)
    phone1 = Column(String, nullable=True)
    phone2 = Column(String, nullable=True)
    block_lot = Column(String, nullable=True)
    street = Column(String, nullable=True)
    village = Column(String, nullable=True)
    city = Column(String, nullable=True)
    region = Column(String, nullable=True)
    zip_code = Column(String, nullable=True)
    country = Column(String, default="Philippines")