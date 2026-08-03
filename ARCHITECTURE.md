# OpenCLI Admin Architecture

## System Overview

```mermaid
graph TB
    subgraph Users["Users"]
        Researcher["Researcher/Analyst"]
        Admin["Administrator"]
    end

    subgraph Frontend["Frontend (Next.js)"]
        UI["Web UI<br/>Port 3010"]
        Canvas["Visual Workflow Canvas<br/>Dify-style"]
        Dashboard["Project Dashboard"]
        Evidence["Evidence & Galaxy View"]
    end

    subgraph Backend["Backend (FastAPI)"]
        API["REST API<br/>Port 8031"]
        WS["WebSocket Server"]
        Auth["Authentication<br/>Token-based"]
        Scheduler["Task Scheduler"]
    end

    subgraph Workers["Execution Layer"]
        subgraph Agents["Agents"]
            LocalAgent["Local Agent"]
            RemoteAgent["Remote Agent<br/>WS Reverse Channel"]
        end

        subgraph Browser["Browser Fleet"]
            Chromium["Chromium + noVNC<br/>Port 6080"]
            Bridge["Bridge / CDP"]
        end

        subgraph Collectors["Data Collectors"]
            OpenCLI["OpenCLI Adapters"]
            RSS["RSS Feeds"]
            API_Collector["REST API"]
            Web["Web Scraping"]
        end
    end

    subgraph Processing["Processing Pipeline"]
        Normalize["Normalization"]
        Deduplicate["Deduplication"]
        AI["AI Processing<br/>Summary / Tags"]
        Relations["Relationship Extraction"]
        Quality["Quality Gates"]
    end

    subgraph Storage["Data Storage"]
        PostgreSQL["PostgreSQL<br/>Projects, Workflows,<br/>Runs, Records"]
        Redis["Redis<br/>Task Queue,<br/>Cache"]
        Files["File Storage<br/>Artifacts, Screenshots"]
    end

    subgraph Delivery["Delivery"]
        Webhook["Webhooks"]
        Feishu["Feishu"]
        DingTalk["DingTalk"]
        WeCom["WeCom"]
        Email["Email"]
        MCP["MCP Server"]
    end

    Users --> UI
    UI --> Canvas
    UI --> Dashboard
    UI --> Evidence

    Canvas --> API
    Dashboard --> API
    Evidence --> API

    API --> Auth
    API --> Scheduler
    API --> WS

    Scheduler --> Workers
    Workers --> Browser
    Workers --> Collectors

    Collectors --> Processing
    Processing --> Storage

    Processing --> Delivery

    style Frontend fill:#1a1a2e,stroke:#4a4a6a,color:#fff
    style Backend fill:#16213e,stroke:#4a4a6a,color:#fff
    style Workers fill:#0f3460,stroke:#4a4a6a,color:#fff
    style Processing fill:#533483,stroke:#4a4a6a,color:#fff
    style Storage fill:#2d1b69,stroke:#4a4a6a,color:#fff
```

## Core Components

### 1. Frontend (Next.js)

- **Visual Workflow Canvas**: Dify-style node-based workflow editor
- **Project Dashboard**: Project overview, run history, data browser
- **Evidence & Galaxy View**: Relationship visualization and exploration
- **Plugin Center**: Capability discovery and configuration

### 2. Backend (FastAPI)

- **REST API**: Full CRUD for projects, workflows, runs, records
- **WebSocket Server**: Real-time run events and trace streaming
- **Authentication**: Token-based auth (BOOTSTRAP_ADMIN_TOKEN, API_AUTH_TOKEN)
- **Scheduler**: Cron-like scheduled workflow execution

### 3. Execution Layer

- **Local Agent**: Built-in browser execution on host
- **Remote Agent**: Remote execution via WebSocket reverse channel
- **Browser Fleet**: Dockerized Chromium with noVNC for login-required sites
- **Bridge/CDP**: Chrome DevTools Protocol for browser control

### 4. Data Collectors

- **OpenCLI Adapters**: 229+ site-specific adapters
- **RSS Feeds**: Standard RSS/Atom feed collection
- **REST API**: Generic API polling
- **Web Scraping**: Custom scraping logic

### 5. Processing Pipeline

- **Normalization**: Standardize data formats across sources
- **Deduplication**: Content-based deduplication
- **AI Processing**: LLM-powered summarization and tagging
- **Relationship Extraction**: Entity and relationship identification
- **Quality Gates**: Configurable data quality rules

### 6. Delivery

- **Webhooks**: HTTP callbacks to external systems
- **IM Integrations**: Feishu, DingTalk, WeCom
- **Email**: SMTP delivery
- **MCP Server**: Model Context Protocol for AI agents

## Workflow Lifecycle

```mermaid
stateDiagram-v2
    [*] --> Draft: Create workflow
    Draft --> Validated: Validate
    Validated --> Published: Publish version
    Published --> Running: Execute
    Running --> Completed: Success
    Running --> Failed: Error
    Completed --> [*]
    Failed --> [*]

    note right of Published
        Immutable versions
        v1, v2, v3...
    end note

    note right of Running
        Node-level events
        Trace logging
        Retry logic
    end note
```

## Data Model

```mermaid
erDiagram
    Project ||--o{ Workflow : has
    Workflow ||--o{ WorkflowVersion : versions
    WorkflowVersion ||--o{ Run : executes
    Run ||--o{ NodeEvent : contains
    Run ||--o{ Record : produces
    Record ||--o{ Evidence : generates
    Evidence ||--o{ Relationship : forms

    Project {
        string id
        string name
        string template
        json config
    }

    Workflow {
        string id
        string project_id
        string name
        json nodes
        json edges
    }

    Run {
        string id
        string version_id
        string status
        datetime started_at
        datetime completed_at
    }

    Record {
        string id
        string run_id
        string source_type
        json raw_data
        json normalized
    }
```

## Deployment Architecture

```mermaid
graph TB
    subgraph Docker["Docker Compose"]
        subgraph App["opencli-admin"]
            API["FastAPI Backend<br/>Port 8031"]
            Web["Next.js Frontend<br/>Port 3010"]
            Worker["Celery Worker"]
        end

        subgraph Browser["Browser Container"]
            Chromium["Chromium + noVNC<br/>Port 6080"]
        end

        subgraph DB["Database"]
            PostgreSQL["PostgreSQL 15"]
            Redis["Redis 7"]
        end
    end

    subgraph External
        Users["Users"]
        Internet["Internet Sources"]
        IM["IM Platforms"]
    end

    Users --> Web
    Users --> API
    Web --> API
    API --> DB
    API --> Worker
    Worker --> Browser
    Browser --> Internet
    Worker --> IM
```

## Key Design Decisions

1. **Self-Hosted First**: All data stays on user's infrastructure
2. **Visual Workflows**: Non-technical users can build pipelines without code
3. **Immutable Versions**: Published workflow versions are immutable for reproducibility
4. **Evidence-Centric**: All collected data linked to evidence and relationships
5. **Dry-Run Default**: Safe execution with explicit publish step
6. **Multi-Architecture**: Docker images for amd64 and arm64

## Technology Stack

- **Frontend**: Next.js 14, React, TypeScript
- **Backend**: FastAPI, Python 3.11+
- **Database**: PostgreSQL 15, Redis 7
- **Task Queue**: Celery
- **Browser**: Chromium, noVNC, Playwright
- **Container**: Docker, Docker Compose
- **AI Processing**: OpenAI-compatible API (configurable)

## File Structure

```
opencli-admin/
├── frontend/               # Next.js frontend
│   ├── src/
│   │   ├── app/           # App router pages
│   │   ├── components/    # React components
│   │   └── lib/           # Utilities
│   └── package.json
├── backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/           # API routes
│   │   ├── core/          # Core logic
│   │   ├── models/        # Database models
│   │   └── services/      # Business logic
│   └── requirements.txt
├── workers/                # Celery workers
├── scripts/                # Installation scripts
├── docker-compose.yml      # Container orchestration
├── Dockerfile              # Container definition
└── docs/                   # Documentation
```
