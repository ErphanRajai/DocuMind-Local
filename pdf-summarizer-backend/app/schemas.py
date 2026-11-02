from datetime import datetime
from typing import Annotated, Literal, Optional
from urllib.parse import urlparse
import os

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
DocumentID = Annotated[int, Field(gt=0)]


class PDFDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    status: str
    summary: Optional[str] = None
    error_message: Optional[str] = None
    warning_message: Optional[str] = None
    page_count: Optional[int] = None
    source_version: int = 0
    created_at: datetime


class GenerationSettings(BaseModel):
    answer_language: str = Field(default='auto', pattern=r'^(auto|[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?)$')
    answer_length: Literal["short", "long"] = "short"
    model: Optional[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]] = None
    provider: Literal["ollama", "openai-compatible"] = "ollama"
    api_base_url: Optional[str] = Field(default=None, max_length=2048)
    api_key: Optional[str] = Field(default=None, max_length=4096, repr=False)

    @model_validator(mode="after")
    def validate_provider(self):
        if os.getenv('DOCUMIND_LOCAL_ONLY') == '1' and self.provider != 'ollama':
            raise ValueError('This installation is local-only. Hosted model providers are disabled.')
        if os.getenv('DOCUMIND_LOCAL_ONLY') == '1' and self.model and 'cloud' in self.model.lower():
            raise ValueError('Cloud-backed Ollama models are disabled in local-only mode.')
        if self.provider == "openai-compatible":
            if not self.api_key or not self.api_key.strip() or not self.api_base_url:
                raise ValueError("Add an API endpoint and API key in Model settings.")
            try:
                parsed = urlparse(self.api_base_url.strip())
                local_hosts = {"localhost", "127.0.0.1", "::1", "host.docker.internal"}
                valid = parsed.hostname and not parsed.username and not parsed.password and (
                    parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname.lower() in local_hosts)
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("Provider URL must use HTTPS, or HTTP on a local address, without embedded credentials.")
        return self


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(max_length=16000)]


class ChatRequest(GenerationSettings):
    search_mode: Literal['fast', 'deep'] = 'fast'
    focus_problem: str = Field(default='', max_length=1200)
    pdf_id: Optional[DocumentID] = None
    pdf_ids: list[DocumentID] = Field(default_factory=list, max_length=3)
    question: Question
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_context(self):
        self.pdf_ids = list(dict.fromkeys(self.pdf_ids + ([self.pdf_id] if self.pdf_id else [])))
        if len(self.pdf_ids) > 3:
            raise ValueError("Select at most three PDFs.")
        if sum(len(message.content) for message in self.history) + len(self.question) > 64000:
            raise ValueError("Conversation context is too long. Start a new conversation or shorten the messages.")
        return self


class SummaryRequest(GenerationSettings):
    mode: Literal["quick", "complete", "synthesis"] = "quick"
    pdf_ids: list[DocumentID] = Field(min_length=1, max_length=3)
    custom_prompt: Optional[Question] = None

    @model_validator(mode="after")
    def unique_documents(self):
        self.pdf_ids = list(dict.fromkeys(self.pdf_ids))
        return self


class PreloadRequest(BaseModel):
    model: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class JobRequest(BaseModel):
    kind: Literal["chat", "summary"]
    payload: ChatRequest | SummaryRequest

    @model_validator(mode="before")
    @classmethod
    def choose_payload(cls, data):
        if isinstance(data, dict) and isinstance(data.get("payload"), dict):
            data = dict(data)
            model = ChatRequest if data.get("kind") == "chat" else SummaryRequest
            data["payload"] = model.model_validate(data["payload"])
        return data
