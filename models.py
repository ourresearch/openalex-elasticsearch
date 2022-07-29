from sqlalchemy.orm import declarative_base
from sqlalchemy import Column, Numeric, DateTime

Base = declarative_base()


class Work(Base):
    __table_args__ = {"schema": "mid"}
    __tablename__ = "json_works"

    id = Column(Numeric, primary_key=True)
    updated = Column(DateTime)
