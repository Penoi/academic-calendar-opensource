import re
from datetime import date, datetime, time

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationError, field_validator, model_validator

CODE_RE = re.compile(r"^[a-z0-9_-]{2,20}$")


def normalize_code(raw: str) -> str:
    """'#Math01 ' -> 'math01'"""
    return raw.strip().lstrip("#").lower()


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str


class SubjectIn(BaseModel):
    code: str
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        v = normalize_code(v)
        if not CODE_RE.match(v):
            raise ValueError("código inválido")
        return v

    @field_validator("name")
    @classmethod
    def _name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("nome vazio")
        return v


class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    color: str


class SubscriptionIn(BaseModel):
    code: str


class SubscriptionPatch(BaseModel):
    active: bool


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    subject: SubjectOut
    active: bool


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    date: date
    start_time: time | None = None  # sem horário = dia inteiro
    end_time: time | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("título vazio")
        return v

    @field_validator("description")
    @classmethod
    def _desc(cls, v: str | None) -> str | None:
        return (v or "").strip() or None

    @model_validator(mode="after")
    def _times(self):
        if self.end_time and not self.start_time:
            raise ValueError("informe o horário de início")
        if self.end_time and self.start_time and self.end_time <= self.start_time:
            raise ValueError("o fim precisa ser depois do início")
        return self


class EventUpdate(EventIn):
    version: int


class EventOut(BaseModel):
    id: int
    subject: SubjectOut
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime | None
    all_day: bool
    version: int
    updated_by: str
    updated_at: datetime


class AuditOut(BaseModel):
    id: int
    user: str
    event_id: int | None
    action: str
    before: dict | None
    after: dict | None
    created_at: datetime


FIELD_MESSAGES = {
    "email": "Email inválido.",
    "password": "A senha precisa ter entre 8 e 128 caracteres.",
    "code": "Código inválido: use de 2 a 20 letras minúsculas, números, - ou _.",
    "name": "Dê um nome para a matéria.",
    "color": "Escolha uma cor válida.",
    "title": "Dê um título para o evento (até 200 caracteres).",
    "description": "A descrição pode ter no máximo 2000 caracteres.",
    "date": "Data inválida.",
    "start_time": "Horário de início inválido.",
    "end_time": "Horário de fim inválido.",
    "version": "Versão do evento ausente.",
}


def friendly_error(exc: ValidationError) -> str:
    """Primeira mensagem de erro em português, para mostrar no formulário."""
    err = exc.errors()[0]
    field = str(err["loc"][0]) if err["loc"] else ""
    if field in FIELD_MESSAGES:
        return FIELD_MESSAGES[field]
    msg = str(err.get("msg", "Dados inválidos."))
    msg = msg.removeprefix("Value error, ")
    return msg[:1].upper() + msg[1:] + ("" if msg.endswith(".") else ".")
