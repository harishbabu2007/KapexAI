from typing import Literal

from pydantic import ConfigDict, EmailStr, BaseModel, Field


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

class BusinessProfileRequest(BaseModel):
    your_name: str = ""
    industry: str = ""
    about_you: str = ""
    business_history: str = ""
    location: str = ""
    monthly_income: str = ""
    monthly_expenditure: str = ""

# Categories offered by the feedback dialog. The sheet stores these verbatim.
FeedbackCategory = Literal["bug", "feature_request", "general"]

# Hard cap on the stored (trimmed) message. The field below is given a looser
# schema bound so an over-long paste produces a readable error message instead of
# a bare validation dump, while still bounding what a client can send.
MAX_FEEDBACK_MESSAGE_CHARS = 2000
_FEEDBACK_MESSAGE_INPUT_BOUND = MAX_FEEDBACK_MESSAGE_CHARS * 2

MAX_FEEDBACK_SESSION_ID_CHARS = 64
MAX_FEEDBACK_PAGE_PATH_INPUT_CHARS = 256


class FeedbackRequest(BaseModel):
    """A single feedback submission.

    `extra="forbid"` rejects unknown fields so a client cannot smuggle extra
    data (e.g. a transcript) into the write. The user id and contact email are
    never taken from the body — they come from the authenticated user.
    """

    model_config = ConfigDict(extra="forbid")

    category: FeedbackCategory
    message: str = Field(min_length=1, max_length=_FEEDBACK_MESSAGE_INPUT_BOUND)
    contact_allowed: bool = False
    # Optional: the chat the feedback was sent from. Ownership is verified.
    session_id: str | None = Field(default=None, max_length=MAX_FEEDBACK_SESSION_ID_CHARS)
    page_path: str | None = Field(
        default=None, max_length=MAX_FEEDBACK_PAGE_PATH_INPUT_CHARS
    )