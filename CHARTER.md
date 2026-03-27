# Project Charter: ModelMesh (AI Gateway)

## 1. Project Overview

**Vision:** To create a unified API interface that intelligently routes development requests to the optimal AI model, balancing cost, performance, and capability.

**Primary Goal:** Reduce AI operational costs by utilizing local/free models for simple tasks while reserving expensive proprietary models for complex reasoning.

**Secondary Goal:** Prevent vendor lock-in by abstracting the provider layer.

## 2. Technical Architecture

We will use a **Modular Monolith** architecture initially (easier to develop/test) which can be split into microservices later.

### Tech Stack Recommendation

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Backend Language | Python (FastAPI) | Python is the native language of AI. Libraries like litellm or langchain are Python-first. Handles async requests natively (crucial for streaming AI responses). |
| Database | PostgreSQL | Relational data is best for storing User configs, API keys, and structured Persona data. |
| Cache/Queue | Redis | To handle rate limiting and store temporary chat context (conversation history). |
| Frontend | React + Next.js (or AdminJS) | Move fast with templates, or build custom UI. |
| Infrastructure | Docker | Essential because one of the "Providers" is a local LLM running in a container. |

### System Diagram

```
graph TD
 A[User Client / IDE Plugin] --> B[ModelMesh API Gateway]
 B --> C{Router Engine}
 C -->|Complex Code| D[Adapter: Anthropic]
 C -->|Standard Chat| E[Adapter: OpenAI]
 C -->|Simple Task| F[Adapter: Ollama (Local)]
 D --> G[Claude 3.5 Sonnet]
 E --> H[GPT-4o]
 F --> I[Llama 3 Local Container]
 B --> J[(Postgres DB: Logs/User Config)]
```

## 3. Database Schema Design

### Table: users
- id (UUID)
- email, password_hash
- default_persona_id

### Table: providers
- id (UUID)
- name (e.g., "OpenAI", "Anthropic", "Ollama")
- api_base_url (e.g., "https://api.openai.com/v1" or "http://localhost:11434")
- auth_type (e.g., "Bearer Token", "None")

### Table: models
- id (UUID)
- provider_id (FK)
- model_name (e.g., "gpt-4", "claude-3-5-sonnet")
- cost_per_1k_tokens (Decimal)
- capabilities (JSON - e.g., {"vision": true, "context_window": 200000})

### Table: personas
- id (UUID)
- user_id (FK)
- name (e.g., "Python Architect")
- system_prompt (Text)
- primary_model_id (FK -> models)
- fallback_model_id (FK -> models)
- routing_rules (JSON - e.g., {"max_cost": 0.01, "prefer_local": true})

### Table: request_logs
- id (UUID)
- timestamp
- user_id
- persona_id
- model_used
- input_tokens, output_tokens
- latency_ms
- success (Boolean)

## 4. Development Phases (Sprints)

### Phase 1: The Core & Local Integration (Weeks 1-2)
**Goal:** Prove we can connect to a local model and abstract it.

**Tasks:**
- **Setup Environment:** Docker Compose file containing FastAPI, Postgres, and an Ollama container (running Llama 3).
- **Database Migrations:** Set up Alembic (Python migration tool) and create the schema.
- **The Adapter Pattern:** Create a standard Python class BaseModelAdapter.
- **Ollama Adapter:** Implement the logic to send a prompt to the local Ollama container and stream the response back.
- **Basic API Endpoint:** POST /v1/chat.
  - Logic: Accepts a prompt -> Routes to Ollama Adapter -> Returns text.

**Deliverable:** A running API where you can curl a prompt, and it returns a response from a local Llama model.

### Phase 2: The Multi-Provider Logic (Weeks 3-4)
**Goal:** Integrate cloud providers and create the routing logic.

**Tasks:**
- **OpenAI Adapter:** Implement logic to call OpenAI API. Handle API key security (store keys encrypted in DB).
- **Anthropic Adapter:** Implement logic to call Claude API. Handle their specific headers/auth.
- **Unified Response:** Ensure all adapters return data in the exact same JSON format (OpenAI compatible format is the industry standard).
- **Routing Engine:** Create Router.py.
  - Logic: Check the personas table. If primary_model is available, use it. If not, try fallback_model.
  - Advanced Logic: Implement a "Cost Check." If estimated_tokens * cost > limit, block request or downgrade model.

**Deliverable:** You can switch between GPT-4 and Llama 3 simply by changing the persona_id in your API request.

### Phase 3: Intelligence & Personas (Weeks 5-6)
**Goal:** The "Smart" aspect of the system.

**Tasks:**
- **Persona CRUD:** Create UI or API endpoints to create/update/delete Personas.
- **Context Management:** Implement simple memory. Store the last 10 messages of a chat session in Redis so the AI "remembers" the conversation.
- **Auto-Router (The "Classifier"):**
  - Concept: Before sending the main prompt, send a tiny prompt to a cheap model (e.g., Llama 3 local).
  - Prompt: "Classify this request as: CODE, MATH, or CREATIVE."
  - Action: If CODE -> Route to Claude. If CREATIVE -> Route to GPT.
- **Frontend Dashboard:** Build a simple UI to view request_logs (Cost analysis: "You saved $5.00 today by using local models").

**Deliverable:** A system where you type "Write code for..." and it automatically routes to the best code model, vs typing "Tell a joke" which routes to the local model.

### Phase 4: Resilience & Testing (Weeks 7-8)
**Goal:** Production readiness.

**Tasks:**
- **Integration Tests:** Write a test suite that spins up Docker containers and mocks API calls to OpenAI/Anthropic (so you don't spend money testing).
- **Rate Limiting:** Implement middleware to prevent users from spamming the API (protecting your wallet).
- **Streaming:** Ensure the API supports stream: true (Server-Sent Events) so the UI shows text appearing character-by-character.
- **Documentation:** Write the README.md and API Swagger docs.

## 5. Testing Strategy

### Unit Tests (Pytest)
- Test the Router logic in isolation.
  - Input: "Complex Python request", Config: Cost limit $0.05. Assert: Router selects Claude-3.5-Sonnet.
  - Input: "Simple summary". Assert: Router selects Llama-3-Local.

### Mock Integration Tests
- Use pytest-mock or responses library to mock the external HTTP calls to OpenAI/Anthropic.
- Verify that if OpenAI returns a 500 error, your system catches it and tries the fallback model.

### End-to-End Test
- Run the full stack locally.
- Send a real request to your Local Ollama model.
- Verify the response stream is saved to the database.

## 6. Future Extensions (Post-MVP)

- **Agent Chains:** Allow a request to go to Model A (Writer), then pass the output to Model B (Reviewer/Refactorer) automatically.
- **Billing:** Integrate Stripe to bill users based on token usage.
- **IDE Plugin:** Build a VS Code extension that uses your API instead of Copilot.