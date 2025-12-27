# backend/app/routers/attendance.py
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import sqlite3
from datetime import datetime

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

class StudentAttendance(BaseModel):
    id: int
    name: str
    attendance: List[str]

class AttendanceSheet(BaseModel):
    classId: int
    className: str
    month: int
    year: int
    students: Optional[List[StudentAttendance]] = []
    thresholds: dict

# In-memory storage (replace with real DB later)
attendance_data: dict = {}

@router.post("/save")
async def save_attendance(sheet: AttendanceSheet):
    """Save attendance sheet for class/month"""
    key = f"{sheet.classId}_{sheet.month}_{sheet.year}"
    attendance_data[key] = sheet.dict()
    
    print(f"💾 SAVED: {sheet.className} - {len(sheet.students)} students")
    return {"status": "saved", "key": key, "students_count": len(sheet.students)}

@router.get("/load/{class_id}")
async def load_attendance(
    class_id: int, 
    month: int = Query(1, ge=1, le=12), 
    year: int = Query(2025, ge=2000)
):
    """Load attendance sheet for class/month"""
    key = f"{class_id}_{month}_{year}"
    
    if key in attendance_data:
        print(f"📂 LOADED: Class {class_id} - {month}/{year}")
        return attendance_data[key]
    
    print(f"📭 No data found for: {class_id}/{month}/{year}")
    raise HTTPException(status_code=404, detail="No attendance data found")
