# Persona Configuration

## What is a Persona?

A persona bundles:
- A system prompt (instructions for the AI)
- Primary and fallback models
- Routing rules (cost limits, preferences)
- Memory settings

## Creating a Persona

```bash
curl -X POST http://localhost:18800/v1/personas \
  -H "Authorization: Bearer your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "code-reviewer",
    "description": "Expert code reviewer",
    "system_prompt": "You are an expert code reviewer...",
    "primary_model_id": "uuid-of-claude",
    "fallback_model_id": "uuid-of-gemini",
    "routing_rules": {
      "max_cost": 0.05
    },
    "memory_enabled": true,
    "max_memory_messages": 10
  }'
```

## Routing Rules

| Field | Type | Description |
|-------|------|-------------|
| `max_cost` | float | Maximum estimated cost per request (USD) |
| `prefer_local` | bool | Prefer local models when available |
| `timeout_seconds` | int | Request timeout override |
| `max_tokens` | int | Default max tokens for responses |

## Example Personas

### Quick Helper
Simple tasks, local models preferred:
```json
{
  "name": "quick-helper",
  "primary_model_id": "llama3-uuid",
  "fallback_model_id": "claude-uuid",
  "routing_rules": {"max_cost": 0.01, "prefer_local": true},
  "memory_enabled": true,
  "max_memory_messages": 5
}
```

### Python Architect
Complex code review, expensive models:
```json
{
  "name": "python-architect",
  "system_prompt": "You are an expert Python architect...",
  "primary_model_id": "claude-uuid",
  "fallback_model_id": "gemini-uuid",
  "routing_rules": {"max_cost": 0.10},
  "memory_enabled": true,
  "max_memory_messages": 20
}
```

### Creative Writer
Long-form creative content:
```json
{
  "name": "creative-writer",
  "system_prompt": "You are a creative writing assistant...",
  "primary_model_id": "claude-uuid",
  "routing_rules": {"max_cost": 0.05, "max_tokens": 8192},
  "memory_enabled": true,
  "max_memory_messages": 50
}
```

## Memory Management

- `memory_enabled`: Enable conversation memory (default: true)
- `max_memory_messages`: Number of messages to remember (default: 10)
- Memory is stored in Redis with 24-hour TTL by default
- Memory is cleared when starting a new conversation

## Failover Behavior

When the primary model fails (rate limit, timeout, error):
1. Try fallback model if configured
2. If fallback fails, return error to user
3. Log all attempts for debugging

## Cost Estimation

Costs are estimated before the request:
1. Count tokens in input messages (using tiktoken)
2. Estimate output tokens (2x input heuristic)
3. Calculate: `(input_tokens / 1M * input_cost) + (output_tokens / 1M * output_cost)`
4. Compare against `max_cost` in routing rules

If estimated cost exceeds `max_cost`:
- If fallback model exists, use it
- Otherwise, return `cost_limit_exceeded` error