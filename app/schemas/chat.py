from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    response: str
    extracted_metrics: list[str] | None = None  # список сохранённых типов показателей
