from pydantic import BaseModel


class LoginRequest(BaseModel):
    code: str
    password: str


class FirstAccessRequest(BaseModel):
    code: str
    password: str


class FirstAccessStatusResponse(BaseModel):
    code: str
    found: bool = False
    user_name: str | None = None
    first_access_required: bool


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    user_name: str
    user_code: str
    role: str
    whatsapp: str | None = None
