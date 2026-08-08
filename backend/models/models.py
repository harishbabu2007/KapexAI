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

class QuestionnaireAnswer(BaseModel):
    key: str
    answer: str

class SubmitQuestionnaireAnswersRequest(BaseModel):
    session_id: str
    answers: list[QuestionnaireAnswer]

class SubmitQuestionnaireClarificationRequest(BaseModel):
    session_id: str
    keys: list[str]

class RenameSessionRequest(BaseModel):
    session_id: str
    name: str

class DeleteSessionRequest(BaseModel):
    session_id: str