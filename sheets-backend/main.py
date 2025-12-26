from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import jwt
import hashlib
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
from dotenv import load_dotenv
import ssl
import os

from database import get_db, init_db
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.orm import selectinload
from models import Teacher, Student, Class, Enrollment, StudentRecord, QRSession, ContactMessage

load_dotenv()

app = FastAPI(title="Lernova Attendsheets API")

# Security
security = HTTPBearer()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Email Configuration
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", SMTP_USERNAME)

# Temporary storage for verification codes
verification_codes = {}
password_reset_codes = {}

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "https://lernova-attendsheets-mn.vercel.app",  # ✅ Your actual domain
        "https://lernova-attendsheets-mn-git-main-nabeels-projects-bba4dd9d.vercel.app",  # ✅ Git branch domain
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ==================== PYDANTIC MODELS ====================

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "teacher"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class StudentEnrollmentRequest(BaseModel):
    class_id: str
    name: str
    rollNo: str
    email: EmailStr

class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str

class PasswordResetRequest(BaseModel):
    email: EmailStr

class VerifyResetCodeRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class UpdateProfileRequest(BaseModel):
    name: str

class ChangePasswordRequest(BaseModel):
    code: str
    new_password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str

class TokenResponse(BaseModel):
    access_token: str
    user: UserResponse

class ClassRequest(BaseModel):
    id: int
    name: str
    students: List[Dict[str, Any]]
    customColumns: List[Dict[str, Any]]
    thresholds: Optional[Dict[str, Any]] = None

class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    subject: str
    message: str

class ResendVerificationRequest(BaseModel):
    email: EmailStr

class QRSessionRequest(BaseModel):
    class_id: str
    rotation_interval: int = 5

class ScanQRRequest(BaseModel):
    qr_code: str
    class_id: str

# ==================== HELPER FUNCTIONS ====================

def get_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return get_password_hash(plain_password) == hashed_password

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_verification_code() -> str:
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(to_email: str, code: str, name: str):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Verify Your Lernova Attendsheets Account"
        msg['From'] = f"Lernova Attendsheets <{FROM_EMAIL}>"
        msg['To'] = to_email

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Email Verification</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #a8edea;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: linear-gradient(135deg, #a8edea 0%, #c2f5e9 100%); min-height: 100vh;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1); overflow: hidden;">
                            <tr>
                                <td style="background: linear-gradient(135deg, #16a085 0%, #2ecc71 100%); padding: 50px 40px; text-align: center;">
                                    <h1 style="margin: 0 0 8px 0; color: white; font-size: 28px; font-weight: 600;">Lernova Attendsheets</h1>
                                    <p style="margin: 0; color: white; font-size: 15px; opacity: 0.95;">Modern Attendance Management</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px;">
                                    <h2 style="margin: 0 0 20px 0; color: #2c3e50; font-size: 26px; font-weight: 600;">Welcome, {name}!</h2>
                                    <p style="margin: 0 0 30px 0; color: #7f8c8d; font-size: 15px; line-height: 1.6;">
                                        Thank you for signing up for Lernova Attendsheets. To complete your registration, please verify your email address.
                                    </p>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-bottom: 25px; background: linear-gradient(135deg, #d4f1f4 0%, #c3f0d8 100%); border-radius: 16px;">
                                        <tr>
                                            <td style="padding: 30px; text-align: center;">
                                                <p style="margin: 0 0 15px 0; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; color: #16a085; text-transform: uppercase;">Your Verification Code</p>
                                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: white; border-radius: 12px; margin-bottom: 15px;">
                                                    <tr>
                                                        <td style="padding: 20px; text-align: center;">
                                                            <span style="font-size: 42px; font-weight: 700; letter-spacing: 14px; color: #16a085; font-family: 'Courier New', monospace;">{code}</span>
                                                        </td>
                                                    </tr>
                                                </table>
                                                <p style="margin: 0; font-size: 13px; color: #16a085;">This code will expire in 15 minutes</p>
                                            </td>
                                        </tr>
                                    </table>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: #f8f9fa; border-left: 4px solid #16a085; border-radius: 8px;">
                                        <tr>
                                            <td style="padding: 15px 20px;">
                                                <p style="margin: 0 0 5px 0; color: #2c3e50; font-size: 14px; font-weight: 600;">Security Tip</p>
                                                <p style="margin: 0; color: #7f8c8d; font-size: 13px; line-height: 1.5;">If you didn't create an account with Lernova Attendsheets, you can safely ignore this email.</p>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 30px 40px; text-align: center; border-top: 1px solid #ecf0f1;">
                                    <p style="margin: 0; color: #95a5a6; font-size: 12px;">© 2025 Lernova Attendsheets. All rights reserved.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        part = MIMEText(html, 'html')
        msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def send_password_reset_email(to_email: str, code: str, name: str):
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "Reset Your Lernova Attendsheets Password"
        msg['From'] = f"Lernova Attendsheets <{FROM_EMAIL}>"
        msg['To'] = to_email

        html = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Password Reset</title>
        </head>
        <body style="margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #a8edea;">
            <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: linear-gradient(135deg, #a8edea 0%, #c2f5e9 100%); min-height: 100vh;">
                <tr>
                    <td style="padding: 40px 20px;">
                        <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="max-width: 600px; margin: 0 auto; background: white; border-radius: 20px; box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1); overflow: hidden;">
                            <tr>
                                <td style="background: linear-gradient(135deg, #16a085 0%, #2ecc71 100%); padding: 50px 40px; text-align: center;">
                                    <h1 style="margin: 0 0 8px 0; color: white; font-size: 28px; font-weight: 600;">Password Reset</h1>
                                    <p style="margin: 0; color: white; font-size: 15px; opacity: 0.95;">Lernova Attendsheets</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px;">
                                    <h2 style="margin: 0 0 20px 0; color: #2c3e50; font-size: 26px; font-weight: 600;">Hi {name},</h2>
                                    <p style="margin: 0 0 30px 0; color: #7f8c8d; font-size: 15px; line-height: 1.6;">
                                        We received a request to reset your password. Use the verification code below to set a new password.
                                    </p>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin-bottom: 25px; background: linear-gradient(135deg, #d4f1f4 0%, #c3f0d8 100%); border-radius: 16px;">
                                        <tr>
                                            <td style="padding: 30px; text-align: center;">
                                                <p style="margin: 0 0 15px 0; font-size: 11px; font-weight: 600; letter-spacing: 1.5px; color: #16a085; text-transform: uppercase;">Your Password Reset Code</p>
                                                <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: white; border-radius: 12px; margin-bottom: 15px;">
                                                    <tr>
                                                        <td style="padding: 20px; text-align: center;">
                                                            <span style="font-size: 42px; font-weight: 700; letter-spacing: 14px; color: #16a085; font-family: 'Courier New', monospace;">{code}</span>
                                                        </td>
                                                    </tr>
                                                </table>
                                                <p style="margin: 0; font-size: 13px; color: #16a085;">This code will expire in 15 minutes</p>
                                            </td>
                                        </tr>
                                    </table>
                                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background: #f8f9fa; border-left: 4px solid #e74c3c; border-radius: 8px;">
                                        <tr>
                                            <td style="padding: 15px 20px;">
                                                <p style="margin: 0 0 5px 0; color: #2c3e50; font-size: 14px; font-weight: 600;">Security Alert</p>
                                                <p style="margin: 0; color: #7f8c8d; font-size: 13px; line-height: 1.5;">If you didn't request a password reset, please ignore this email or contact support if you have concerns about your account security.</p>
                                            </td>
                                        </tr>
                                    </table>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 30px 40px; text-align: center; border-top: 1px solid #ecf0f1;">
                                    <p style="margin: 0; color: #95a5a6; font-size: 12px;">© 2025 Lernova Attendsheets. All rights reserved.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """
        
        part = MIMEText(html, 'html')
        msg.attach(part)

        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=context) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, to_email, msg.as_string())
        
        return True
    except Exception as e:
        print(f"Error sending reset email: {e}")
        return False

async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security), db: AsyncSession = Depends(get_db)):
    """Verify JWT token and return user email and role"""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        role: str = payload.get("role")
        
        if email is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
        
        return {"email": email, "role": role}
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials")

async def update_teacher_overview(teacher_id: str, db: AsyncSession):
    """Update teacher's overview statistics"""
    result = await db.execute(
        select(Class).where(Class.teacher_id == teacher_id)
    )
    classes = result.scalars().all()
    
    total_students = 0
    for cls in classes:
        enrollment_result = await db.execute(
            select(func.count(Enrollment.id))
            .where(Enrollment.class_id == cls.id)
            .where(Enrollment.status == "active")
        )
        total_students += enrollment_result.scalar()
    
    await db.execute(
        update(Teacher)
        .where(Teacher.id == teacher_id)
        .values(total_classes=len(classes), total_students=total_students)
    )
    await db.commit()

# ==================== STARTUP EVENT ====================

@app.on_event("startup")
async def startup_event():
    await init_db()

# ==================== ROOT & HEALTH ====================

@app.get("/")
async def read_root():
    return {
        "message": "Lernova Attendsheets API",
        "version": "1.0.0",
        "status": "online",
        "database": "PostgreSQL"
    }

@app.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get database statistics"""
    teacher_count = await db.execute(select(func.count(Teacher.id)))
    student_count = await db.execute(select(func.count(Student.id)))
    class_count = await db.execute(select(func.count(Class.id)))
    
    return {
        "total_users": teacher_count.scalar(),
        "total_students": student_count.scalar(),
        "total_classes": class_count.scalar(),
        "timestamp": datetime.utcnow().isoformat()
    }

# ==================== TEACHER AUTH ENDPOINTS ====================

@app.post("/auth/signup")
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Sign up a new teacher"""
    try:
        # Check if user already exists
        result = await db.execute(select(Teacher).where(Teacher.email == request.email))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User with this email already exists")
        
        if len(request.password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters long")
        
        # Generate verification code
        code = generate_verification_code()
        print(f"Verification code for {request.email}: {code}")
        
        # Store verification data
        verification_codes[request.email] = {
            "code": code,
            "name": request.name,
            "password": get_password_hash(request.password),
            "role": "teacher",
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }
        
        # Send verification email
        email_sent = send_verification_email(request.email, code, request.name)
        
        return {
            "success": True,
            "message": "Verification code sent to your email" if email_sent else f"Code: {code}"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Signup error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Signup failed: {str(e)}")

@app.post("/auth/verify-email", response_model=TokenResponse)
async def verify_email(request: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Verify email with code - handles both teacher and student"""
    try:
        if request.email not in verification_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No verification code found")
        
        stored_data = verification_codes[request.email]
        
        # Check expiration
        expires_at = datetime.fromisoformat(stored_data["expires_at"])
        if datetime.utcnow() > expires_at:
            del verification_codes[request.email]
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired")
        
        # Verify code
        if stored_data["code"] != request.code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        
        role = stored_data.get("role", "teacher")
        
        # Create user based on role
        if role == "student":
            user_id = f"student_{int(datetime.utcnow().timestamp())}"
            new_student = Student(
                id=user_id,
                email=request.email,
                name=stored_data["name"],
                password=stored_data["password"]
            )
            db.add(new_student)
            await db.commit()
            await db.refresh(new_student)
            
            user_data = {"id": new_student.id, "email": new_student.email, "name": new_student.name}
        else:
            user_id = f"user_{int(datetime.utcnow().timestamp())}"
            new_teacher = Teacher(
                id=user_id,
                email=request.email,
                name=stored_data["name"],
                password=stored_data["password"]
            )
            db.add(new_teacher)
            await db.commit()
            await db.refresh(new_teacher)
            
            user_data = {"id": new_teacher.id, "email": new_teacher.email, "name": new_teacher.name}
        
        # Clean up verification code
        del verification_codes[request.email]
        
        # Create access token
        access_token = create_access_token(
            data={"sub": request.email, "role": role},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return TokenResponse(
            access_token=access_token,
            user=UserResponse(**user_data)
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Verification error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Verification failed: {str(e)}")

@app.post("/auth/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login user (teacher or student)"""
    # Try teacher first
    result = await db.execute(select(Teacher).where(Teacher.email == request.email))
    teacher = result.scalar_one_or_none()
    
    if teacher and verify_password(request.password, teacher.password):
        access_token = create_access_token(
            data={"sub": request.email, "role": "teacher"},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return TokenResponse(
            access_token=access_token,
            user=UserResponse(id=teacher.id, email=teacher.email, name=teacher.name)
        )
    
    # Try student
    result = await db.execute(select(Student).where(Student.email == request.email))
    student = result.scalar_one_or_none()
    
    if student and verify_password(request.password, student.password):
        access_token = create_access_token(
            data={"sub": request.email, "role": "student"},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        return TokenResponse(
            access_token=access_token,
            user=UserResponse(id=student.id, email=student.email, name=student.name)
        )
    
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

@app.post("/auth/logout")
async def logout(auth_data: dict = Depends(verify_token)):
    """Logout user"""
    return {"success": True, "message": "Logged out successfully"}

@app.get("/auth/me", response_model=UserResponse)
async def get_current_user(auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get current user info"""
    email = auth_data["email"]
    role = auth_data["role"]
    
    if role == "teacher":
        result = await db.execute(select(Teacher).where(Teacher.email == email))
        user = result.scalar_one_or_none()
    else:
        result = await db.execute(select(Student).where(Student.email == email))
        user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    return UserResponse(id=user.id, email=user.email, name=user.name)

@app.put("/auth/profile")
async def update_profile(request: UpdateProfileRequest, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Update user profile"""
    email = auth_data["email"]
    role = auth_data["role"]
    
    if role == "teacher":
        result = await db.execute(select(Teacher).where(Teacher.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.name = request.name
    else:
        result = await db.execute(select(Student).where(Student.email == email))
        user = result.scalar_one_or_none()
        if user:
            user.name = request.name
    
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    
    await db.commit()
    return UserResponse(id=user.id, email=user.email, name=user.name)

@app.delete("/auth/delete-account")
async def delete_account(auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Delete user account and all associated data"""
    try:
        email = auth_data["email"]
        role = auth_data["role"]
        
        if role == "teacher":
            result = await db.execute(select(Teacher).where(Teacher.email == email))
            user = result.scalar_one_or_none()
            if user:
                await db.delete(user)
        else:
            result = await db.execute(select(Student).where(Student.email == email))
            user = result.scalar_one_or_none()
            if user:
                await db.delete(user)
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        await db.commit()
        return {"success": True, "message": "Account deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Delete account error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete account")

@app.post("/auth/request-password-reset")
async def request_password_reset(request: PasswordResetRequest, db: AsyncSession = Depends(get_db)):
    """Request password reset"""
    # Try teacher
    result = await db.execute(select(Teacher).where(Teacher.email == request.email))
    teacher = result.scalar_one_or_none()
    
    if teacher:
        code = generate_verification_code()
        password_reset_codes[request.email] = {
            "code": code,
            "expires": datetime.utcnow() + timedelta(minutes=10)
        }
        send_password_reset_email(request.email, code, teacher.name)
        return {"message": "Password reset code sent to your email"}
    
    # Try student
    result = await db.execute(select(Student).where(Student.email == request.email))
    student = result.scalar_one_or_none()
    
    if student:
        code = generate_verification_code()
        password_reset_codes[request.email] = {
            "code": code,
            "expires": datetime.utcnow() + timedelta(minutes=10)
        }
        send_password_reset_email(request.email, code, student.name)
        return {"message": "Password reset code sent to your email"}
    
    return {"message": "If the email exists, a reset code has been sent"}

@app.post("/auth/verify-reset-code")
async def verify_reset_code(request: VerifyResetCodeRequest, db: AsyncSession = Depends(get_db)):
    """Verify reset code and change password"""
    if request.email not in password_reset_codes:
        raise HTTPException(status_code=400, detail="Invalid or expired code")
    
    stored_data = password_reset_codes[request.email]
    
    if stored_data["code"] != request.code:
        raise HTTPException(status_code=400, detail="Invalid code")
    
    if datetime.utcnow() > stored_data["expires"]:
        del password_reset_codes[request.email]
        raise HTTPException(status_code=400, detail="Code has expired")
    
    new_password_hash = get_password_hash(request.new_password)
    
    # Try teacher
    result = await db.execute(select(Teacher).where(Teacher.email == request.email))
    teacher = result.scalar_one_or_none()
    
    if teacher:
        teacher.password = new_password_hash
        await db.commit()
        del password_reset_codes[request.email]
        return {"message": "Password updated successfully"}
    
    # Try student
    result = await db.execute(select(Student).where(Student.email == request.email))
    student = result.scalar_one_or_none()
    
    if student:
        student.password = new_password_hash
        await db.commit()
        del password_reset_codes[request.email]
        return {"message": "Password updated successfully"}
    
    raise HTTPException(status_code=404, detail="User not found")

# ==================== STUDENT AUTH ENDPOINTS ====================

@app.post("/auth/student/signup")
async def student_signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """Sign up a new student"""
    try:
        # Check if student already exists
        result = await db.execute(select(Student).where(Student.email == request.email))
        existing_student = result.scalar_one_or_none()
        
        if existing_student:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Student with this email already exists")
        
        # Also check teachers to prevent email conflicts
        result = await db.execute(select(Teacher).where(Teacher.email == request.email))
        existing_teacher = result.scalar_one_or_none()
        
        if existing_teacher:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This email is already registered as a teacher")
        
        if len(request.password) < 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password must be at least 8 characters long")
        
        code = generate_verification_code()
        print(f"Verification code for {request.email}: {code}")
        
        verification_codes[request.email] = {
            "code": code,
            "name": request.name,
            "password": get_password_hash(request.password),
            "role": "student",
            "expires_at": (datetime.utcnow() + timedelta(minutes=15)).isoformat()
        }
        
        email_sent = send_verification_email(request.email, code, request.name)
        
        return {
            "success": True,
            "message": "Verification code sent to your email" if email_sent else f"Code: {code}"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Student signup error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Signup failed: {str(e)}")

@app.post("/auth/student/verify-email", response_model=TokenResponse)
async def verify_student_email(request: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    """Verify student email with code"""
    try:
        if request.email not in verification_codes:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No verification code found")
        
        stored_data = verification_codes[request.email]
        
        if stored_data.get("role") != "student":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification attempt")
        
        expires_at = datetime.fromisoformat(stored_data["expires_at"])
        if datetime.utcnow() > expires_at:
            del verification_codes[request.email]
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification code expired")
        
        if stored_data["code"] != request.code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification code")
        
        student_id = f"student_{int(datetime.utcnow().timestamp())}"
        
        new_student = Student(
            id=student_id,
            email=request.email,
            name=stored_data["name"],
            password=stored_data["password"]
        )
        db.add(new_student)
        await db.commit()
        await db.refresh(new_student)
        
        del verification_codes[request.email]
        
        access_token = create_access_token(
            data={"sub": request.email, "role": "student"},
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )
        
        return TokenResponse(
            access_token=access_token,
            user=UserResponse(id=student_id, email=request.email, name=stored_data["name"])
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Student verification error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Verification failed: {str(e)}")

@app.post("/auth/student/login", response_model=TokenResponse)
async def student_login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login student"""
    result = await db.execute(select(Student).where(Student.email == request.email))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    
    if not verify_password(request.password, user.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    
    access_token = create_access_token(
        data={"sub": request.email, "role": "student"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(id=user.id, email=user.email, name=user.name)
    )

@app.delete("/auth/student/delete-account")
async def delete_student_account(auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Delete student account and all associated data"""
    try:
        print(f"API: Delete student account request for {auth_data['email']}")
        
        result = await db.execute(select(Student).where(Student.email == auth_data["email"]))
        student = result.scalar_one_or_none()
        
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        
        await db.delete(student)
        await db.commit()
        
        print(f"API: Student account deleted successfully")
        return {"success": True, "message": "Student account deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"API: Delete student account error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete student account")

# ==================== CLASS ENDPOINTS ====================

@app.get("/classes")
async def get_classes(auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get all classes for the current teacher"""
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access classes")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    result = await db.execute(
        select(Class)
        .where(Class.teacher_id == user.id)
        .options(selectinload(Class.student_records))
    )
    classes = result.scalars().all()
    
    response_classes = []
    for cls in classes:
        # Get active enrollments
        enrollment_result = await db.execute(
            select(Enrollment)
            .where(Enrollment.class_id == cls.id)
            .where(Enrollment.status == "active")
        )
        active_enrollments = enrollment_result.scalars().all()
        active_record_ids = {e.student_record_id for e in active_enrollments}
        
        # Filter to only active students
        active_students = [
            {
                "id": sr.id,
                "name": sr.name,
                "rollNo": sr.roll_no,
                "email": sr.email,
                "attendance": sr.attendance or {}
            }
            for sr in cls.student_records
            if sr.id in active_record_ids
        ]
        
        # Calculate statistics
        total_students = len(active_students)
        thresholds = cls.thresholds or {
            "excellent": 95.0,
            "good": 90.0,
            "moderate": 85.0,
            "atRisk": 85.0
        }
        
        at_risk = 0
        excellent = 0
        total_attendance = 0.0
        
        for student in active_students:
            attendance = student["attendance"]
            if attendance:
                present = sum(1 for v in attendance.values() if v in ["P", "L"])
                total = len(attendance)
                percentage = (present / total * 100.0) if total > 0 else 0.0
                total_attendance += percentage
                
                if percentage >= thresholds.get("excellent", 95.0):
                    excellent += 1
                elif percentage < thresholds.get("moderate", 85.0):
                    at_risk += 1
        
        avg_attendance = (total_attendance / total_students) if total_students > 0 else 0.0
        
        response_classes.append({
            "id": cls.id,
            "name": cls.name,
            "teacher_id": cls.teacher_id,
            "students": active_students,
            "customColumns": cls.custom_columns or [],
            "thresholds": thresholds,
            "statistics": {
                "total_students": total_students,
                "avg_attendance": round(avg_attendance, 3),
                "at_risk_count": at_risk,
                "excellent_count": excellent
            },
            "created_at": cls.created_at.isoformat() if cls.created_at else None,
            "updated_at": cls.updated_at.isoformat() if cls.updated_at else None
        })
    
    return {"classes": response_classes}

@app.post("/classes")
async def create_class(class_data: ClassRequest, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Create a new class"""
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can create classes")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    class_id = str(class_data.id)
    
    # Check if class already exists
    result = await db.execute(select(Class).where(Class.id == class_id))
    existing_class = result.scalar_one_or_none()
    
    if existing_class:
        raise HTTPException(status_code=400, detail="Class with this ID already exists")
    
    # Create class
    new_class = Class(
        id=class_id,
        name=class_data.name,
        teacher_id=user.id,
        custom_columns=class_data.customColumns,
        thresholds=class_data.thresholds or {
            "excellent": 95.0,
            "good": 90.0,
            "moderate": 85.0,
            "atRisk": 85.0
        }
    )
    db.add(new_class)
    
    # Add students
    for student_data in class_data.students:
        student_record = StudentRecord(
            id=student_data.get("id"),
            class_id=class_id,
            name=student_data.get("name"),
            roll_no=student_data.get("rollNo"),
            email=student_data.get("email"),
            attendance=student_data.get("attendance", {})
        )
        db.add(student_record)
    
    await db.commit()
    await update_teacher_overview(user.id, db)
    
    return {"success": True, "class": {"id": class_id, "name": class_data.name}}

@app.get("/classes/{class_id}")
async def get_class(class_id: str, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get a specific class"""
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access classes")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    result = await db.execute(
        select(Class)
        .where(Class.id == class_id)
        .where(Class.teacher_id == user.id)
        .options(selectinload(Class.student_records))
    )
    cls = result.scalar_one_or_none()
    
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    
    # Get active enrollments
    enrollment_result = await db.execute(
        select(Enrollment)
        .where(Enrollment.class_id == class_id)
        .where(Enrollment.status == "active")
    )
    active_enrollments = enrollment_result.scalars().all()
    active_record_ids = {e.student_record_id for e in active_enrollments}
    
    # Filter to only active students
    active_students = [
        {
            "id": sr.id,
            "name": sr.name,
            "rollNo": sr.roll_no,
            "email": sr.email,
            "attendance": sr.attendance or {}
        }
        for sr in cls.student_records
        if sr.id in active_record_ids
    ]
    
    return {
        "class": {
            "id": cls.id,
            "name": cls.name,
            "teacher_id": cls.teacher_id,
            "students": active_students,
            "customColumns": cls.custom_columns or [],
            "thresholds": cls.thresholds,
            "created_at": cls.created_at.isoformat() if cls.created_at else None,
            "updated_at": cls.updated_at.isoformat() if cls.updated_at else None
        }
    }

@app.put("/classes/{class_id}")
async def update_class(class_id: str, class_data: ClassRequest, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Update a class - handles student deletions AND preserves inactive student data"""
    print("=" * 60)
    print(f"[UPDATE_CLASS] Starting update for class {class_id}")
    print("=" * 60)
    
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can update classes")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Get class
    result = await db.execute(
        select(Class)
        .where(Class.id == class_id)
        .where(Class.teacher_id == user.id)
        .options(selectinload(Class.student_records))
    )
    cls = result.scalar_one_or_none()
    
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    
    # Get ALL students in file (both active and inactive)
    all_students_in_file = cls.student_records
    print(f"[UPDATE_CLASS] Students in FILE: {len(all_students_in_file)}")
    for s in all_students_in_file:
        attendance_count = len(s.attendance or {})
        print(f"  - ID: {s.id}, Name: {s.name}, Attendance: {attendance_count}")
    
    # Get incoming students from request
    incoming_students = class_data.students
    print(f"[UPDATE_CLASS] Students in REQUEST: {len(incoming_students)}")
    for s in incoming_students:
        attendance_count = len(s.get("attendance", {}))
        print(f"  - ID: {s.get('id')}, Name: {s.get('name')}, Attendance: {attendance_count}")
    
    # Find deleted students
    current_student_ids = {s.id for s in all_students_in_file}
    new_student_ids = {s.get("id") for s in incoming_students}
    deleted_student_ids = current_student_ids - new_student_ids
    
    print(f"[UPDATE_CLASS] Analysis:")
    print(f"  - Current IDs: {current_student_ids}")
    print(f"  - New IDs: {new_student_ids}")
    print(f"  - Deleted IDs: {deleted_student_ids}")
    
    if deleted_student_ids:
        print(f"[UPDATE_CLASS] Students DELETED by teacher: {deleted_student_ids}")
        
        # Mark deleted students as inactive in enrollments
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.class_id == class_id)
            .where(Enrollment.student_record_id.in_(deleted_student_ids))
            .where(Enrollment.status == "active")
        )
        enrollments_to_deactivate = result.scalars().all()
        
        for enrollment in enrollments_to_deactivate:
            old_status = enrollment.status
            enrollment.status = "inactive"
            enrollment.removed_by_teacher_at = datetime.utcnow()
            print(f"  - Marked enrollment {enrollment.student_record_id} as inactive (was {old_status})")
    
    # Update class info
    cls.name = class_data.name
    cls.custom_columns = class_data.customColumns
    cls.thresholds = class_data.thresholds
    cls.updated_at = datetime.utcnow()
    
    # Build final student list (active + inactive preserved)
    updated_students_map = {s.get("id"): s for s in incoming_students}
    
    print(f"[UPDATE_CLASS] Building final student list:")
    for student in all_students_in_file:
        student_id = student.id
        if student_id in updated_students_map:
            # Active student - update from request
            updated = updated_students_map[student_id]
            student.name = updated.get("name")
            student.roll_no = updated.get("rollNo")
            student.email = updated.get("email")
            student.attendance = updated.get("attendance", {})
            print(f"  ✓ Including ACTIVE: {student.name} (ID: {student_id}) - Attendance: {len(student.attendance)}")
        else:
            # Inactive student - preserve from file
            print(f"  ✓ Preserving INACTIVE: {student.name} (ID: {student_id}) - Attendance: {len(student.attendance or {})}")
    
    await db.commit()
    await update_teacher_overview(user.id, db)
    
    # Verification
    await db.refresh(cls)
    print(f"[UPDATE_CLASS] Verification: File now has {len(cls.student_records)} students")
    
    # Return only active students to frontend
    enrollment_result = await db.execute(
        select(Enrollment)
        .where(Enrollment.class_id == class_id)
        .where(Enrollment.status == "active")
    )
    active_enrollments = enrollment_result.scalars().all()
    active_record_ids = {e.student_record_id for e in active_enrollments}
    
    active_students = [
        {
            "id": sr.id,
            "name": sr.name,
            "rollNo": sr.roll_no,
            "email": sr.email,
            "attendance": sr.attendance or {}
        }
        for sr in cls.student_records
        if sr.id in active_record_ids
    ]
    
    response_data = {
        "id": cls.id,
        "name": cls.name,
        "students": active_students,
        "customColumns": cls.custom_columns,
        "thresholds": cls.thresholds,
        "teacher_id": user.id,
        "created_at": cls.created_at.isoformat() if cls.created_at else None,
        "updated_at": cls.updated_at.isoformat()
    }
    
    return {"success": True, "class": response_data}

@app.delete("/classes/{class_id}")
async def delete_class(class_id: str, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Delete a class"""
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can delete classes")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    result = await db.execute(
        select(Class)
        .where(Class.id == class_id)
        .where(Class.teacher_id == user.id)
    )
    cls = result.scalar_one_or_none()
    
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    
    await db.delete(cls)
    await db.commit()
    await update_teacher_overview(user.id, db)
    
    return {"success": True, "message": "Class deleted successfully"}

@app.get("/overview")
async def get_overview(auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get teacher overview"""
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can access overview")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return {
        "total_classes": user.total_classes,
        "total_students": user.total_students,
        "last_updated": datetime.utcnow().isoformat()
    }

# ==================== STUDENT ENROLLMENT ENDPOINTS ====================

@app.post("/student/enroll")
async def enroll_in_class(request: StudentEnrollmentRequest, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Enroll student in a class"""
    try:
        if auth_data["role"] != "student":
            raise HTTPException(status_code=403, detail="Only students can enroll")
        
        result = await db.execute(select(Student).where(Student.email == auth_data["email"]))
        student = result.scalar_one_or_none()
        
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        
        if request.email != auth_data["email"]:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You must use your registered email")
        
        # Check if class exists
        result = await db.execute(select(Class).where(Class.id == request.class_id))
        cls = result.scalar_one_or_none()
        
        if not cls:
            raise HTTPException(status_code=404, detail="Class not found")
        
        # Check if already actively enrolled
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student.id)
            .where(Enrollment.class_id == request.class_id)
            .where(Enrollment.status == "active")
        )
        active_enrollment = result.scalar_one_or_none()
        
        if active_enrollment:
            raise HTTPException(status_code=400, detail="You are already enrolled in this class")
        
        # Check if was enrolled before (re-enrollment)
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student.id)
            .where(Enrollment.class_id == request.class_id)
        )
        previous_enrollment = result.scalar_one_or_none()
        
        if previous_enrollment:
            # RE-ENROLLMENT
            print(f"[RE-ENROLLMENT] Reactivating enrollment")
            previous_enrollment.status = "active"
            previous_enrollment.re_enrolled_at = datetime.utcnow()
            previous_enrollment.roll_no = request.rollNo
            
            # Get student record
            result = await db.execute(
                select(StudentRecord)
                .where(StudentRecord.id == previous_enrollment.student_record_id)
            )
            student_record = result.scalar_one_or_none()
            
            if student_record:
                student_record.name = request.name
                student_record.roll_no = request.rollNo
                attendance_count = len(student_record.attendance or {})
                message = f"Welcome back! Your {attendance_count} attendance records have been restored."
            else:
                # Create if missing
                student_record = StudentRecord(
                    id=previous_enrollment.student_record_id,
                    class_id=request.class_id,
                    name=request.name,
                    roll_no=request.rollNo,
                    email=request.email,
                    attendance={}
                )
                db.add(student_record)
                message = "Re-enrolled successfully"
            
            await db.commit()
            await update_teacher_overview(cls.teacher_id, db)
            
            return {"success": True, "message": message, "enrollment": {"status": "re-enrolled"}}
        
        else:
            # NEW ENROLLMENT
            print(f"[NEW ENROLLMENT] Creating new enrollment")
            student_record_id = int(datetime.utcnow().timestamp() * 1000)
            
            # Create student record
            new_record = StudentRecord(
                id=student_record_id,
                class_id=request.class_id,
                name=request.name,
                roll_no=request.rollNo,
                email=request.email,
                attendance={}
            )
            db.add(new_record)
            
            # Create enrollment
            new_enrollment = Enrollment(
                student_id=student.id,
                class_id=request.class_id,
                student_record_id=student_record_id,
                roll_no=request.rollNo,
                status="active"
            )
            db.add(new_enrollment)
            
            await db.commit()
            await update_teacher_overview(cls.teacher_id, db)
            
            return {"success": True, "message": "Successfully enrolled in class!", "enrollment": {"status": "enrolled"}}
    
    except ValueError as e:
        error_message = str(e)
        print(f"[ENROLL_ENDPOINT] ValueError: {error_message}")
        if "already enrolled" in error_message.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error_message)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ENROLL_ENDPOINT] ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to enroll in class")

@app.delete("/student/unenroll/{class_id}")
async def unenroll_from_class(class_id: str, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Unenroll student from a class"""
    try:
        if auth_data["role"] != "student":
            raise HTTPException(status_code=403, detail="Only students can unenroll")
        
        result = await db.execute(select(Student).where(Student.email == auth_data["email"]))
        student = result.scalar_one_or_none()
        
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        
        # Find active enrollment
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student.id)
            .where(Enrollment.class_id == class_id)
            .where(Enrollment.status == "active")
        )
        enrollment = result.scalar_one_or_none()
        
        if not enrollment:
            raise HTTPException(status_code=400, detail="You are not enrolled in this class")
        
        # Mark as inactive (preserve data)
        enrollment.status = "inactive"
        enrollment.unenrolled_at = datetime.utcnow()
        
        # Get class for teacher update
        result = await db.execute(select(Class).where(Class.id == class_id))
        cls = result.scalar_one_or_none()
        
        await db.commit()
        
        if cls:
            await update_teacher_overview(cls.teacher_id, db)
        
        return {"success": True, "message": "Successfully unenrolled from class"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Unenrollment error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to unenroll from class: {str(e)}")

@app.get("/student/classes")
async def get_student_classes(auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get all classes a student is enrolled in"""
    try:
        if auth_data["role"] != "student":
            raise HTTPException(status_code=403, detail="Only students can access this")
        
        result = await db.execute(select(Student).where(Student.email == auth_data["email"]))
        student = result.scalar_one_or_none()
        
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student.id)
            .where(Enrollment.status == "active")
            .options(selectinload(Enrollment.class_obj).selectinload(Class.teacher))
        )
        enrollments = result.scalars().all()
        
        classes_details = []
        for enrollment in enrollments:
            cls = enrollment.class_obj
            teacher = cls.teacher if cls else None
            teacher_name = teacher.name if teacher else "Unknown"
            
            # Get student record details
            result = await db.execute(
                select(StudentRecord)
                .where(StudentRecord.id == enrollment.student_record_id)
            )
            student_record = result.scalar_one_or_none()
            
            if student_record:
                attendance = student_record.attendance or {}
                present = sum(1 for v in attendance.values() if v == "P")
                absent = sum(1 for v in attendance.values() if v == "A")
                late = sum(1 for v in attendance.values() if v == "L")
                total = len(attendance)
                percentage = ((present + late) / total * 100) if total > 0 else 0.0
                
                thresholds = cls.thresholds or {
                    "excellent": 95.0,
                    "good": 90.0,
                    "moderate": 85.0,
                    "atRisk": 85.0
                }
                
                if percentage >= thresholds.get("excellent", 95.0):
                    status = "excellent"
                elif percentage >= thresholds.get("good", 90.0):
                    status = "good"
                elif percentage >= thresholds.get("moderate", 85.0):
                    status = "moderate"
                else:
                    status = "at risk"
                
                class_info = {
                    "class_id": cls.id,
                    "class_name": cls.name,
                    "teacher_name": teacher_name,
                    "enrolled_at": enrollment.enrolled_at.isoformat() if enrollment.enrolled_at else None,
                    "re_enrolled_at": enrollment.re_enrolled_at.isoformat() if enrollment.re_enrolled_at else None,
                    "student_record": {
                        "id": student_record.id,
                        "name": student_record.name,
                        "rollNo": student_record.roll_no,
                        "email": student_record.email,
                        "attendance": attendance
                    },
                    "thresholds": thresholds,
                    "statistics": {
                        "total_classes": total,
                        "present": present,
                        "absent": absent,
                        "late": late,
                        "percentage": round(percentage, 3),
                        "status": status
                    }
                }
                classes_details.append(class_info)
        
        return {"classes": classes_details}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching student classes: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch classes")

@app.get("/student/class/{class_id}")
async def get_student_class_detail(class_id: str, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get detailed information about a specific class"""
    try:
        if auth_data["role"] != "student":
            raise HTTPException(status_code=403, detail="Only students can access this")
        
        result = await db.execute(select(Student).where(Student.email == auth_data["email"]))
        student = result.scalar_one_or_none()
        
        if not student:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
        
        # Get enrollment
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student.id)
            .where(Enrollment.class_id == class_id)
            .where(Enrollment.status == "active")
        )
        enrollment = result.scalar_one_or_none()
        
        if not enrollment:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found or student not enrolled")
        
        # Get class
        result = await db.execute(select(Class).where(Class.id == class_id))
        cls = result.scalar_one_or_none()
        
        if not cls:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
        
        # Get student record
        result = await db.execute(
            select(StudentRecord)
            .where(StudentRecord.id == enrollment.student_record_id)
        )
        student_record = result.scalar_one_or_none()
        
        if not student_record:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student record not found")
        
        # Calculate statistics
        attendance = student_record.attendance or {}
        present = sum(1 for v in attendance.values() if v == "P")
        absent = sum(1 for v in attendance.values() if v == "A")
        late = sum(1 for v in attendance.values() if v == "L")
        total = len(attendance)
        percentage = ((present + late) / total * 100) if total > 0 else 0.0
        
        thresholds = cls.thresholds or {
            "excellent": 95.0,
            "good": 90.0,
            "moderate": 85.0,
            "atRisk": 85.0
        }
        
        if percentage >= thresholds.get("excellent", 95.0):
            status = "excellent"
        elif percentage >= thresholds.get("good", 90.0):
            status = "good"
        elif percentage >= thresholds.get("moderate", 85.0):
            status = "moderate"
        else:
            status = "at risk"
        
        return {
            "class": {
                "class_id": cls.id,
                "class_name": cls.name,
                "teacher_id": cls.teacher_id,
                "student_record": {
                    "id": student_record.id,
                    "name": student_record.name,
                    "rollNo": student_record.roll_no,
                    "email": student_record.email,
                    "attendance": attendance
                },
                "thresholds": thresholds,
                "statistics": {
                    "total_classes": total,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "percentage": round(percentage, 3),
                    "status": status
                }
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching class details: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to fetch class details")

@app.get("/class/verify/{class_id}")
async def verify_class_exists(class_id: str, db: AsyncSession = Depends(get_db)):
    """Verify if a class exists (public endpoint for enrollment)"""
    try:
        result = await db.execute(select(Class).where(Class.id == class_id))
        class_data = result.scalar_one_or_none()
        
        if not class_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
        
        # Get teacher info
        teacher_id = class_data.teacher_id
        teacher_name = "Unknown"
        if teacher_id:
            result = await db.execute(select(Teacher).where(Teacher.id == teacher_id))
            teacher = result.scalar_one_or_none()
            if teacher:
                teacher_name = teacher.name
        
        return {
            "exists": True,
            "class_name": class_data.name,
            "teacher_name": teacher_name,
            "class_id": class_id
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error verifying class: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to verify class")

# ==================== QR CODE ATTENDANCE ENDPOINTS ====================

@app.post("/qr/start-session")
async def start_qr_session(request: dict, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Start QR attendance session"""
    class_id = request.get("class_id")
    rotation_interval = request.get("rotation_interval", 5)
    
    print(f"[API] QR start request: class_id={class_id}")
    
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can start QR sessions")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Verify class belongs to teacher
    result = await db.execute(
        select(Class)
        .where(Class.id == class_id)
        .where(Class.teacher_id == user.id)
    )
    cls = result.scalar_one_or_none()
    
    if not cls:
        raise HTTPException(status_code=404, detail="Class not found")
    
    # Check if active session exists
    result = await db.execute(
        select(QRSession)
        .where(QRSession.class_id == class_id)
        .where(QRSession.status == "active")
    )
    existing_session = result.scalar_one_or_none()
    
    if existing_session:
        # Update existing session
        existing_session.current_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        existing_session.code_generated_at = datetime.utcnow()
        existing_session.rotation_interval = rotation_interval
        await db.commit()
        
        return {
            "success": True,
            "session": {
                "class_id": class_id,
                "current_code": existing_session.current_code,
                "attendance_date": existing_session.attendance_date,
                "started_at": existing_session.started_at.isoformat(),
                "rotation_interval": existing_session.rotation_interval,
                "status": "active"
            }
        }
    
    # Create new session
    today = datetime.now().strftime("%Y-%m-%d")
    qr_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    
    new_session = QRSession(
        class_id=class_id,
        teacher_id=user.id,
        current_code=qr_code,
        attendance_date=today,
        rotation_interval=rotation_interval,
        status="active",
        scanned_students=[]
    )
    db.add(new_session)
    await db.commit()
    
    return {
        "success": True,
        "session": {
            "class_id": class_id,
            "current_code": qr_code,
            "attendance_date": today,
            "started_at": new_session.started_at.isoformat(),
            "rotation_interval": rotation_interval,
            "status": "active"
        }
    }

@app.get("/qr/session/{class_id}")
async def get_qr_session(class_id: str, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Get current QR session"""
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    result = await db.execute(
        select(QRSession)
        .where(QRSession.class_id == class_id)
        .where(QRSession.status == "active")
    )
    session = result.scalar_one_or_none()
    
    if not session:
        return {"active": False}
    
    if session.teacher_id != user.id:
        return {"active": False}
    
    # Auto-rotate code if needed
    elapsed = (datetime.utcnow() - session.code_generated_at).total_seconds()
    
    if elapsed >= session.rotation_interval:
        session.current_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        session.code_generated_at = datetime.utcnow()
        await db.commit()
    
    return {
        "active": True,
        "session": {
            "class_id": session.class_id,
            "current_code": session.current_code,
            "attendance_date": session.attendance_date,
            "started_at": session.started_at.isoformat(),
            "rotation_interval": session.rotation_interval,
            "scanned_students": session.scanned_students or [],
            "status": session.status
        }
    }

@app.post("/qr/scan")
async def scan_qr_code(class_id: str, qr_code: str, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Student scans QR code to mark attendance"""
    try:
        if auth_data["role"] != "student":
            raise HTTPException(status_code=403, detail="Only students can scan QR codes")
        
        result = await db.execute(select(Student).where(Student.email == auth_data["email"]))
        student = result.scalar_one_or_none()
        
        if not student:
            raise HTTPException(status_code=404, detail="Student not found")
        
        # Get active session
        result = await db.execute(
            select(QRSession)
            .where(QRSession.class_id == class_id)
            .where(QRSession.status == "active")
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=400, detail="No active QR session")
        
        if session.current_code != qr_code:
            raise HTTPException(status_code=400, detail="Invalid or expired QR code")
        
        # Get enrollment
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.student_id == student.id)
            .where(Enrollment.class_id == class_id)
            .where(Enrollment.status == "active")
        )
        enrollment = result.scalar_one_or_none()
        
        if not enrollment:
            raise HTTPException(status_code=403, detail="Not enrolled in this class")
        
        # Get student record
        result = await db.execute(
            select(StudentRecord)
            .where(StudentRecord.id == enrollment.student_record_id)
        )
        student_record = result.scalar_one_or_none()
        
        if not student_record:
            raise HTTPException(status_code=404, detail="Student record not found")
        
        # Mark attendance
        attendance = student_record.attendance or {}
        attendance[session.attendance_date] = "P"
        student_record.attendance = attendance
        
        # Add to scanned list
        scanned = session.scanned_students or []
        if student_record.id not in scanned:
            scanned.append(student_record.id)
            session.scanned_students = scanned
        
        await db.commit()
        
        return {
            "message": "Attendance marked as Present",
            "date": session.attendance_date
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"QR scan error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to scan QR code")

@app.post("/qr/stop-session")
async def stop_qr_session(payload: dict, auth_data: dict = Depends(verify_token), db: AsyncSession = Depends(get_db)):
    """Stop QR session and mark non-scanned students as absent"""
    class_id = payload.get("class_id")
    if not class_id:
        raise HTTPException(status_code=400, detail="class_id required")
    
    if auth_data["role"] != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can stop QR sessions")
    
    result = await db.execute(select(Teacher).where(Teacher.email == auth_data["email"]))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        # Get session
        result = await db.execute(
            select(QRSession)
            .where(QRSession.class_id == class_id)
            .where(QRSession.status == "active")
            .where(QRSession.teacher_id == user.id)
        )
        session = result.scalar_one_or_none()
        
        if not session:
            raise HTTPException(status_code=404, detail="No active session found")
        
        # Get all active enrollments
        result = await db.execute(
            select(Enrollment)
            .where(Enrollment.class_id == class_id)
            .where(Enrollment.status == "active")
        )
        enrollments = result.scalars().all()
        
        active_record_ids = {e.student_record_id for e in enrollments}
        scanned_ids = set(session.scanned_students or [])
        
        # Mark absents
        marked_absent = 0
        for record_id in active_record_ids:
            if record_id not in scanned_ids:
                result = await db.execute(
                    select(StudentRecord).where(StudentRecord.id == record_id)
                )
                student_record = result.scalar_one_or_none()
                
                if student_record:
                    attendance = student_record.attendance or {}
                    if session.attendance_date not in attendance:
                        attendance[session.attendance_date] = "A"
                        student_record.attendance = attendance
                        marked_absent += 1
        
        # Stop session
        session.status = "stopped"
        session.stopped_at = datetime.utcnow()
        
        await db.commit()
        
        return {
            "scanned_count": len(scanned_ids),
            "absent_count": marked_absent,
            "date": session.attendance_date
        }
    except Exception as e:
        print(f"[QR_STOP] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to stop QR session")

# ==================== CONTACT ENDPOINT ====================

@app.post("/contact")
async def submit_contact(request: ContactRequest, db: AsyncSession = Depends(get_db)):
    """Submit contact form"""
    try:
        message = ContactMessage(
            email=request.email,
            name=request.name,
            subject=request.subject,
            message=request.message
        )
        db.add(message)
        await db.commit()
        
        return {"success": True, "message": "Message received successfully"}
    except Exception as e:
        print(f"Contact form error: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to process contact form")

# ==================== RUN SERVER ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
