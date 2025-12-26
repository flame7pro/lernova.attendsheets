from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, JSON, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

class Teacher(Base):
    __tablename__ = "teachers"
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    verified = Column(Boolean, default=True)
    role = Column(String, default="teacher")
    total_classes = Column(Integer, default=0)
    total_students = Column(Integer, default=0)
    
    # Relationships
    classes = relationship("Class", back_populates="teacher", cascade="all, delete-orphan")

class Student(Base):
    __tablename__ = "students"
    
    id = Column(String, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    verified = Column(Boolean, default=True)
    role = Column(String, default="student")
    
    # Relationships
    enrollments = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")

class Class(Base):
    __tablename__ = "classes"
    
    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    teacher_id = Column(String, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    custom_columns = Column(JSON, default=list)
    thresholds = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    teacher = relationship("Teacher", back_populates="classes")
    enrollments = relationship("Enrollment", back_populates="class_obj", cascade="all, delete-orphan")
    student_records = relationship("StudentRecord", back_populates="class_obj", cascade="all, delete-orphan")
    qr_sessions = relationship("QRSession", back_populates="class_obj", cascade="all, delete-orphan")

class Enrollment(Base):
    __tablename__ = "enrollments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String, ForeignKey("students.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(String, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    student_record_id = Column(Integer, ForeignKey("student_records.id", ondelete="CASCADE"), nullable=False)
    roll_no = Column(String, nullable=False)
    enrolled_at = Column(DateTime, default=datetime.utcnow)
    unenrolled_at = Column(DateTime, nullable=True)
    re_enrolled_at = Column(DateTime, nullable=True)
    removed_by_teacher_at = Column(DateTime, nullable=True)
    status = Column(String, default="active")  # active, inactive
    
    # Relationships
    student = relationship("Student", back_populates="enrollments")
    class_obj = relationship("Class", back_populates="enrollments")
    student_record = relationship("StudentRecord", foreign_keys=[student_record_id])

class StudentRecord(Base):
    __tablename__ = "student_records"
    
    id = Column(Integer, primary_key=True, autoincrement=True)  # This is student_record_id
    class_id = Column(String, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    roll_no = Column(String, nullable=False)
    email = Column(String, nullable=False)
    attendance = Column(JSON, default=dict)  # {"2025-01-15": "P", "2025-01-16": "A"}
    
    # Relationships
    class_obj = relationship("Class", back_populates="student_records")

class QRSession(Base):
    __tablename__ = "qr_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    class_id = Column(String, ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, unique=True)
    teacher_id = Column(String, ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False)
    current_code = Column(String, nullable=False)
    attendance_date = Column(String, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    stopped_at = Column(DateTime, nullable=True)
    code_generated_at = Column(DateTime, default=datetime.utcnow)
    rotation_interval = Column(Integer, default=5)
    scanned_students = Column(JSON, default=list)  # List of student_record_ids
    status = Column(String, default="active")  # active, stopped
    
    # Relationships
    class_obj = relationship("Class", back_populates="qr_sessions")

class ContactMessage(Base):
    __tablename__ = "contact_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    subject = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
