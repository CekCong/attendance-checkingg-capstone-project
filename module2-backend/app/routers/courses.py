from datetime import datetime
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, String, Text, Boolean, Float, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# -----------------------------------------------------------------------------
# 1. Database Setup
# -----------------------------------------------------------------------------
DATABASE_URL = "postgresql://postgres:password@localhost:5432/postgres"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -----------------------------------------------------------------------------
# 2. SQLAlchemy Model
# -----------------------------------------------------------------------------
class Course(Base):
    __tablename__ = "courses"

    id = Column(String(36), primary_key=True)
    code = Column(String(20), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    semester = Column(String(20), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    venue_latitude = Column(Float, nullable=True)
    venue_longitude = Column(Float, nullable=True)
    venue_name = Column(String(255), nullable=True)
    geofence_radius_meters = Column(Float, default=100.0)
    require_face_recognition = Column(Boolean, default=False)
    require_device_binding = Column(Boolean, default=True)
    risk_threshold = Column(Float, default=0.5)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

# -----------------------------------------------------------------------------
# 3. Pydantic Schemas
# -----------------------------------------------------------------------------
class CourseResponse(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    semester: str
    is_active: bool
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = 100.0
    require_face_recognition: Optional[bool] = False
    require_device_binding: Optional[bool] = True
    risk_threshold: Optional[float] = 0.5
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CourseUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    semester: Optional[str] = None
    is_active: Optional[bool] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_face_recognition: Optional[bool] = None
    require_device_binding: Optional[bool] = None
    risk_threshold: Optional[float] = None

# -----------------------------------------------------------------------------
# 4. API Endpoints Implementation
# -----------------------------------------------------------------------------
app = FastAPI()

# GET /courses - List courses
@app.get("/courses", response_model=List[CourseResponse], status_code=status.HTTP_200_OK)
def list_courses(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(10, ge=1, le=100, description="Pagination limit"),
    is_active: Optional[bool] = Query(None, description="Filter active courses"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    db: Session = Depends(get_db)
):
    query = db.query(Course)
    if is_active is not None:
        query = query.filter(Course.is_active == is_active)
    if semester:
        query = query.filter(Course.semester == semester)
    
    return query.offset(skip).limit(limit).all()


# GET /courses/{id} - Course details
@app.get("/courses/{id}", response_model=CourseResponse, status_code=status.HTTP_200_OK)
def get_course_details(id: str, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{id}' not found."
        )
    return course


# PATCH /courses/{id} - Update course
@app.patch("/courses/{id}", response_model=CourseResponse, status_code=status.HTTP_200_OK)
def update_course(id: str, payload: CourseUpdate, db: Session = Depends(get_db)):
    course = db.query(Course).filter(Course.id == id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{id}' not found."
        )

    # Exclude fields that were not explicitly set in the request
    update_data = payload.model_dump(exclude_unset=True)
    
    for key, value in update_data.items():
        setattr(course, key, value)

    try:
        db.commit()
        db.refresh(course)
        return course
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update course: {str(e)}"
        )