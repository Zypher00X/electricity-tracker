import re

from pydantic import BaseModel, EmailStr, Field, field_validator

# Schemas สำหรับการสมัครสมาชิกผู้ใช้ใหม่
class RegisterRequest(BaseModel):
    full_name: str = Field(
        min_length=2,
        max_length=100,
    )

    email: EmailStr

    phone: str

    password: str = Field(
        min_length=8,
        max_length=128,
    )

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        value = value.strip()

        if len(value) < 2:
            raise ValueError("กรุณากรอกชื่อ - นามสกุล")

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:

        # อนุญาตให้กรอกเช่น 081-234-5678
        # แล้วแปลงเป็น 0812345678
        phone = re.sub(r"\D", "", value)

        if len(phone) != 10:
            raise ValueError(
                "เบอร์โทรศัพท์ต้องมี 10 หลัก"
            )

        if not phone.startswith("0"):
            raise ValueError(
                "รูปแบบเบอร์โทรศัพท์ไม่ถูกต้อง"
            )

        return phone


class RegisterUserResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: str
    role: str
    status: str
    created_at: str


class RegisterResponse(BaseModel):
    message: str
    user: RegisterUserResponse

# =========================================
# schemas สำหรับการเข้าสู่ระบบผู้ใช้
# =========================================

class LoginRequest(BaseModel):
    identifier: str = Field(
        min_length=1,
        max_length=255,
    )

    password: str = Field(
        min_length=1,
        max_length=128,
    )


class LoginUserResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: str
    role: str
    status: str


class LoginResponse(BaseModel):
    message: str
    user: LoginUserResponse


class CurrentUserResponse(BaseModel):
    user_id: str
    full_name: str
    email: str
    phone: str
    role: str
    status: str


class MeResponse(BaseModel):
    user: CurrentUserResponse