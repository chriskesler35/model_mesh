# ModelMesh

Intelligent AI gateway that routes requests to optimal models based on cost, capability, and persona configuration.

## Features

- **Unified API** - OpenAI-compatible interface for Ollama, Anthropic, Google Gemini, and OpenRouter
- **Intelligent Routing** - Personas bundle model selection, prompts, and routing rules
- **Auto-Routing** - Classifies requests (CODE/MATH/CREATIVE/SIMPLE/ANALYSIS) and routes to optimal model
- **Conversation Memory** - Redis-backed session memory for context continuity
- **Cost Tracking** - Real-time token counting and cost estimation across all providers
- **Rate Limiting** - Redis-backed sliding window (60 req/min, 1000 req/hour per API key)
- **Failover** - Automatic fallback to alternative models on error
- **Streaming** - Real-time token streaming for all providers (SSE)
- **Usage Dashboard** - Cost and usage analytics by model/provider
- **VS Code Extension** - IDE integration for development workflow

## Quick Start

```bash
# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start services
docker-compose up -d

# Run migrations
docker-compose exec backend alembic upgrade head

# Seed default data
docker-compose exec backend python -m app.scripts.seed

# Open dashboard
open http://localhost:18801
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│ VS Code     │     │ Dashboard   │     │ API Clients │
│ Extension   │     │ (Next.js)   │     │ (curl, etc) │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           ▼
                  ┌─────────────────┐
                  │   FastAPI       │
                  │   (Port 18800)  │
                  └────────┬────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
  ┌──────────┐      ┌──────────┐      ┌──────────┐
  │ LiteLLM   │      │  Redis   │      │PostgreSQL│
  │(Providers)│      │(Memory)  │      │  (Data)  │
  └──────────┘      └──────────┘      └──────────┘
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `POSTGRES_PASSWORD` | PostgreSQL password | Required |
| `REDIS_PASSWORD` | Redis password | Required |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `GOOGLE_API_KEY` | Google API key | Required |
| `MODELMESH_API_KEY` | Application API key | `modelmesh_local_dev_key` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |

### Providers

ModelMesh supports:
- **Ollama** (local and cloud)
- **Anthropic** (Claude)
- **Google** (Gemini)

## Development

```bash
# Backend
cd backend
python -m venv venv
source venv/bin/activate  # or `.\venv\Scripts\activate` on Windows
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --port 18800

# Frontend
cd frontend
npm install
npm run dev

# Extension
cd extension
npm install
npm run compile
# Press F5 in VS Code to launch extension development host
```

## Documentation

- [API Documentation](docs/api.md)
- [Deployment Guide](docs/deployment.md)
- [Persona Configuration](docs/personas.md)
- [Design Specification](docs/superpowers/specs/2026-03-27-modelmesh-design.md)

## License

MIT