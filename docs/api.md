# ModelMesh API Documentation

## Authentication

All API requests require a Bearer token in the Authorization header:

```
Authorization: Bearer your-api-key
```

For development, use: `modelmesh_local_dev_key`

## Base URL

```
http://localhost:18800/v1
```

## Endpoints

### Chat Completions

**POST /v1/chat/completions**

OpenAI-compatible chat completions endpoint.

**Request:**
```json
{
  "model": "python-architect",
  "messages": [
    {"role": "user", "content": "Write a Python function to sort a list"}
  ],
  "stream": true,
  "conversation_id": "uuid",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

**Response (streaming):**
```
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":"Here"},"index":0}]}
data: {"id":"chatcmpl-xxx","choices":[{"delta":{"content":" is"},"index":0}]}
data: [DONE]
```

**Response (non-streaming):**
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "model": "claude-sonnet-4-6",
  "choices": [{
    "index": 0,
    "message": {"role": "assistant", "content": "..."},
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 150,
    "completion_tokens": 500,
    "total_tokens": 650
  },
  "modelmesh": {
    "persona_used": "python-architect",
    "actual_model": "claude-sonnet-4-6",
    "estimated_cost": 0.0023,
    "provider": "anthropic"
  }
}
```

### Personas

**GET /v1/personas**

List all personas with pagination.

**POST /v1/personas**

Create a new persona.

**GET /v1/personas/{id}**

Get persona by ID or name.

**PATCH /v1/personas/{id}**

Update a persona.

**DELETE /v1/personas/{id}**

Delete a persona.

### Models

**GET /v1/models**

List all available models.

**GET /v1/models/{id}**

Get model by ID or model ID.

### Conversations

**GET /v1/conversations**

List conversations.

**POST /v1/conversations**

Create a conversation.

**GET /v1/conversations/{id}/messages**

Get messages for a conversation.

**DELETE /v1/conversations/{id}**

Delete a conversation.

### Stats

**GET /v1/stats/costs?days=7**

Get cost summary.

**GET /v1/stats/usage?days=7**

Get usage summary.

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "type": "invalid_request_error",
    "message": "Human-readable error message",
    "code": "error_code",
    "details": {}
  }
}
```

### Error Codes

- `persona_not_found` - Persona doesn't exist
- `model_unavailable` - Model is inactive
- `all_models_failed` - All models in failover chain failed
- `cost_limit_exceeded` - Request exceeds max_cost
- `invalid_api_key` - Invalid or missing API key