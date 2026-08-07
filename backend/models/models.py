from pydantic import EmailStr, BaseModel


class WaitlistSignup(BaseModel):
    email: EmailStr
    name: str | None = None

class GoogleTokenRequest(BaseModel):
    credential: str

class CreateChatSession(BaseModel):
    content: str

class UserChatMessage(BaseModel):
    session_id: str
    content: str

class RenameSessionRequest(BaseModel):
    session_id: str
    name: str

class DeleteSessionRequest(BaseModel):
    session_id: str