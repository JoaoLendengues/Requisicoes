from pydantic import BaseModel


class LoginRequest(BaseModel):
    code: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: int
    user_name: str
    user_code: str
    role: str
