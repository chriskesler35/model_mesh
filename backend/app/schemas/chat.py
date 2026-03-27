"""Chat completion schemas."""

from typing import Optional, List
from pydantic import BaseModel, UUID4


class ChatMessage(BaseModel):
    """Chat message."""
    role: str  # 'user', 'assistant', 'system'
    content: str


class ChatCompletionRequest(BaseModel):
    """Chat completion request (OpenAI-compatible)."""
    model: str  # Persona name or model ID
    messages: List[ChatMessage]
    stream: bool = True
    conversation_id: Optional[UUID4] = None
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 4096


class ChatCompletionChoice(BaseModel):
    """Chat completion choice."""
    index: int
    message: ChatMessage
    finish_reason: str


class Usage(BaseModel):
    """Token usage."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ModelMeshMeta(BaseModel):
    """ModelMesh-specific metadata."""
    persona_used: Optional[str] = None
    actual_model: str
    estimated_cost: float
    provider: str


class ChatCompletionResponse(BaseModel):
    """Chat completion response (OpenAI-compatible)."""
    id: str
    object: str = "chat.completion"
    model: str
    choices: List[ChatCompletionChoice]
    usage: Usage
    modelmesh: ModelMeshMeta


class ChatCompletionStreamDelta(BaseModel):
    """Streaming delta."""
    content: Optional[str] = None
    role: Optional[str] = None


class ChatCompletionStreamChoice(BaseModel):
    """Streaming choice."""
    index: int
    delta: ChatCompletionStreamDelta
    finish_reason: Optional[str] = None


class ChatCompletionStreamResponse(BaseModel):
    """Streaming response."""
    id: str
    object: str = "chat.completion.chunk"
    model: str
    choices: List[ChatCompletionStreamChoice]