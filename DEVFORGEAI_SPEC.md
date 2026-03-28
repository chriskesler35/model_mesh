# AgentMesh — Agentic AI Platform Specification
> Formerly ModelMesh — To be renamed based on new capabilities
> Version: 2.0 | Date: 2026-03-28

## 1. Vision

**From Gateway to Agentic Platform**

ModelMesh today is a gateway — it routes requests to AI models.

**AgentMesh** will be an autonomous agentic platform that:
- Breaks complex goals into multi-step workflows
- Orchestrates multiple specialized agents working in parallel
- Generates, reviews, and refines its own output
- Creates visual assets (images, logos, banners)
- Delivers complete solutions, not just chat responses

**The user should never need another AI tool.**

---

## 2. Core Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Interface                          │
│  (Chat, Voice, File Upload, Image Generation)               │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Agent Orchestrator                        │
│  • Task decomposition                                         │
│  • Agent spawning & coordination                             │
│  • Progress tracking                                          │
│  • Result synthesis                                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────┬──────────────┬──────────────┬───────────────┐
│   Coder      │   Researcher │   Designer   │   Reviewer    │
│   Agent      │   Agent      │   Agent     │   Agent       │
│   (Code)     │   (Search)   │   (Images)   │   (Quality)   │
└──────────────┴──────────────┴──────────────┴───────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      ModelMesh Core                          │
│  • Model routing & failover                                  │
│  • Cost optimization                                         │
│  • Memory & context management                               │
│  • Token tracking                                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────┬──────────────┬──────────────┬───────────────┐
│   Claude     │   Gemini     │   OpenAI     │   Local       │
│   (Code)     │   (Images)   │   (Chat)     │   (Free)      │
└──────────────┴──────────────┴──────────────┴───────────────┘
```

---

## 3. Agent Types

### 3.1 Built-in Agents

| Agent | Purpose | Default Model | Capabilities |
|-------|---------|---------------|--------------|
| **Coder** | Write, debug, review code | Claude Sonnet | Code generation, refactoring, testing |
| **Researcher** | Search, summarize, analyze | Gemini Pro | Web search, document analysis, fact-checking |
| **Designer** | Create images, logos, banners | Gemini Nano Banana | Image generation, editing |
| **Reviewer** | Quality check, suggest improvements | Claude Sonnet | Code review, writing critique |
| **Planner** | Break down complex tasks | Claude Sonnet | Task decomposition, workflow design |
| **Executor** | Run tools, API calls | Claude Sonnet | File operations, HTTP requests, shell commands |
| **Writer** | Create content, documentation | Claude Sonnet | Copywriting, docs, summaries |

### 3.2 Agent Configuration

```json
{
  "agent_type": "coder",
  "name": "Python Architect",
  "model": "claude-sonnet-4-6",
  "system_prompt": "You are an expert Python architect...",
  "tools": ["read_file", "write_file", "run_tests", "git_commit"],
  "memory_enabled": true,
  "max_iterations": 10,
  "timeout_seconds": 300
}
```

---

## 4. Workflow Engine

### 4.1 Workflow Definition

```json
{
  "workflow_id": "build-landing-page",
  "trigger": "user_request",
  "trigger_keywords": ["build landing page", "create website", "design page"],
  "steps": [
    {
      "step_id": "research",
      "agent": "researcher",
      "task": "Research best practices for {{topic}} landing pages",
      "output_key": "research_findings"
    },
    {
      "step_id": "copy",
      "agent": "writer",
      "task": "Write landing page copy based on research",
      "input_keys": ["research_findings"],
      "output_key": "copy_content"
    },
    {
      "step_id": "design",
      "agent": "designer",
      "task": "Create landing page design and logo",
      "parallel": true,
      "output_keys": ["design_specs", "logo_image"]
    },
    {
      "step_id": "code",
      "agent": "coder",
      "task": "Build the landing page HTML/CSS",
      "input_keys": ["copy_content", "design_specs"],
      "output_key": "html_code"
    },
    {
      "step_id": "review",
      "agent": "reviewer",
      "task": "Review the complete landing page",
      "input_keys": ["html_code", "logo_image"],
      "output_key": "review_notes",
      "on_failure": "retry_with_feedback"
    }
  ],
  "final_output": ["html_code", "logo_image", "review_notes"]
}
```

### 4.2 Parallel Execution

Multiple agents can run simultaneously:
- Researcher gathers info
- Designer creates images
- Writer drafts copy

All results merge before the coder starts.

---

## 5. Image Generation

### 5.1 Supported Models

| Provider | Model | Capabilities |
|----------|-------|--------------|
| **Google** | Gemini Nano Banana | Image generation, editing, variations |
| **OpenAI** | DALL-E 3 | Image generation |
| **Anthropic** | Claude (vision) | Image understanding (not generation) |

### 5.2 Image Generation API

```http
POST /v1/images/generations
{
  "model": "gemini-nano-banana",
  "prompt": "Create a modern minimalist logo for a SaaS company called AgentMesh",
  "size": "1024x1024",
  "format": "png",
  "style": "minimalist",
  "num_variations": 3
}

Response:
{
  "images": [
    {
      "id": "img_abc123",
      "url": "/v1/images/img_abc123",
      "base64": "...",
      "revised_prompt": "A clean geometric logo..."
    }
  ]
}
```

### 5.3 Inline Image Display

The chat interface will:
1. Detect image responses
2. Display inline (not as links)
3. Show download/save buttons
4. Allow drag-and-drop to save

```tsx
// Chat message rendering
{message.type === 'image' && (
  <div className="image-container">
    <img src={message.url} alt={message.prompt} />
    <div className="image-actions">
      <button onClick={() => downloadImage(message.id)}>💾 Save</button>
      <button onClick={() => copyImage(message.url)}>📋 Copy</button>
      <button onClick={() => generateVariation(message.id)}>🔄 Variations</button>
    </div>
  </div>
)}
```

### 5.4 Image Storage

- Images stored in `/data/images/{user_id}/{conversation_id}/`
- Metadata in PostgreSQL `images` table
- CDN-ready URLs for production

---

## 6. Database Schema Additions

### 6.1 Agents Table

```sql
CREATE TABLE agents (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES user_profiles(id),
    name VARCHAR(255),
    agent_type VARCHAR(50), -- 'coder', 'researcher', 'designer', etc.
    model_id UUID REFERENCES models(id),
    system_prompt TEXT,
    tools JSONB,
    memory_enabled BOOLEAN DEFAULT true,
    max_iterations INTEGER DEFAULT 10,
    timeout_seconds INTEGER DEFAULT 300,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 6.2 Workflows Table

```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES user_profiles(id),
    name VARCHAR(255),
    description TEXT,
    trigger_keywords JSONB,
    steps JSONB, -- Array of step definitions
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 6.3 Workflow Runs Table

```sql
CREATE TABLE workflow_runs (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    conversation_id UUID REFERENCES conversations(id),
    status VARCHAR(50), -- 'pending', 'running', 'completed', 'failed'
    current_step INTEGER,
    step_results JSONB, -- Results from each step
    final_output JSONB,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP
);
```

### 6.4 Images Table

```sql
CREATE TABLE images (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES user_profiles(id),
    conversation_id UUID REFERENCES conversations(id),
    message_id UUID REFERENCES messages(id),
    model VARCHAR(100), -- 'gemini-nano-banana', 'dall-e-3'
    prompt TEXT,
    revised_prompt TEXT,
    format VARCHAR(10), -- 'png', 'jpg', 'webp'
    width INTEGER,
    height INTEGER,
    file_path TEXT,
    url TEXT,
    metadata JSONB, -- Style, variations, etc.
    created_at TIMESTAMP
);
```

---

## 7. API Endpoints

### 7.1 Agent Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/agents` | List all agents |
| POST | `/v1/agents` | Create custom agent |
| GET | `/v1/agents/{id}` | Get agent details |
| PATCH | `/v1/agents/{id}` | Update agent |
| DELETE | `/v1/agents/{id}` | Delete agent |
| POST | `/v1/agents/{id}/run` | Run agent with task |

### 7.2 Workflow Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/v1/workflows` | List workflows |
| POST | `/v1/workflows` | Create workflow |
| GET | `/v1/workflows/{id}` | Get workflow |
| POST | `/v1/workflows/{id}/run` | Execute workflow |
| GET | `/v1/workflows/runs/{id}` | Get run status |

### 7.3 Image Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/v1/images/generations` | Generate image |
| GET | `/v1/images/{id}` | Get image |
| DELETE | `/v1/images/{id}` | Delete image |
| POST | `/v1/images/{id}/variations` | Create variations |
| POST | `/v1/images/{id}/edit` | Edit image |

---

## 8. Frontend Updates

### 8.1 Chat Interface

- **Image display inline** — Images appear in chat, not as links
- **Download buttons** — Save images locally
- **Copy to clipboard** — Copy image or URL
- **Generate variations** — Create alternative versions
- **Agent status** — Show which agents are working

### 8.2 Agent Manager Page

- View all agents
- Create custom agents
- Configure agent tools and prompts
- See agent usage stats

### 8.3 Workflow Builder

- Visual workflow editor
- Drag-and-drop agent steps
- Conditional branching
- Parallel execution paths

### 8.4 Image Gallery

- View all generated images
- Filter by conversation, date, type
- Download, share, delete
- Regenerate from prompt history

---

## 9. Implementation Phases

### Phase 9: Image Generation (Week 1)
- Add Gemini Nano Banana model
- Create `/v1/images/generations` endpoint
- Store images in filesystem/database
- Display images inline in chat
- Download/save functionality

### Phase 10: Agent System (Week 2)
- Create agents table and API
- Implement agent runner
- Add tool execution (read_file, write_file, etc.)
- Agent memory and context sharing

### Phase 11: Workflow Engine (Week 3)
- Create workflows table
- Implement workflow orchestrator
- Add parallel execution
- Progress tracking and status
- Error handling and retry

### Phase 12: UI Enhancements (Week 4)
- Agent status indicators in chat
- Image gallery page
- Workflow builder UI
- Download/save buttons for images

---

## 10. Renaming Consideration

Current name: **ModelMesh**
- Implies "mesh of models" — just routing

New name options:
- **AgentMesh** — Mesh of agents working together
- **MeshAI** — Unified AI platform
- **NexusAI** — Central hub for AI work
- **ForgeAI** — Build/forge solutions with AI
- **CascadeAI** — Agents cascade through tasks

**Recommendation:** **AgentMesh** — Maintains the "Mesh" branding while emphasizing the agentic nature.

---

## 11. Self-Branding Feature

When building this application, the system should automatically generate:
- **Logo** — Based on the name and concept
- **Badge** — Small icon for favicon
- **Banner** — Wide format for social sharing
- **Color scheme** — Derived from the logo

This happens during project initialization using the Designer agent with Gemini Nano Banana.

---

## 12. Questions for Review

1. **Name:** Do you want to rename to AgentMesh, or keep ModelMesh?
2. **Image model:** Confirm Gemini Nano Banana for images?
3. **Workflow complexity:** Start with simple linear workflows, or go straight to parallel/branching?
4. **Tool execution:** Which tools should agents have access to? (file I/O, git, HTTP, shell?)
5. **Priority:** Should I start with image generation (Phase 9) or agent orchestration (Phase 10)?

---

*This spec is ready for your review. Once approved, I'll begin implementation.*