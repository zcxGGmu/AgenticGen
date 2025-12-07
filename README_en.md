# AgenticGen - AI Programming Assistant

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Introduction

AgenticGen is a powerful interactive AI programming assistant designed to provide intelligent programming support for developers. By integrating advanced AI technologies and rich toolsets, AgenticGen significantly improves development efficiency and code quality.

### Core Features

- 🤖 **Intelligent Chat** - Natural language interaction based on GPT-4, understands complex programming requirements
- 🐍 **Code Execution** - Secure Python code execution environment with data analysis and visualization support
- 🗃️ **Knowledge Base** - Support for multiple document formats with RAG (Retrieval Augmented Generation)
- 🗄️ **Database Interaction** - Natural language to SQL conversion with intelligent query optimization
- 📝 **Document Processing** - Automatic parsing and processing of PDF, Word, Excel, and other documents
- 🚀 **Streaming Response** - Real-time streaming output for smooth interaction experience
- 🔐 **Secure Authentication** - Comprehensive identity verification and permission management
- 💾 **High-Performance Caching** - Redis caching system for optimized response speed

## Quick Start

### Prerequisites

- Python 3.11+
- MySQL 5.7+
- Redis 6.0+
- OpenAI API Key

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/zcxGGmu/AgenticGen.git
cd AgenticGen
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env file to configure database and API keys
```

4. **Initialize database**
```bash
# Create database in MySQL
CREATE DATABASE agenticgen CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

# Start the application (tables will be created automatically)
python -m api.main
```

5. **Access the application**
Open your browser and visit http://localhost:9000

### Docker Deployment

```bash
# Quick deployment with docker-compose
docker-compose up -d
```

## System Architecture

AgenticGen adopts a modular microservice architecture design with the following core modules:

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                              │
│                   (HTML/CSS/JavaScript)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                       API Layer                              │
│                      (FastAPI)                               │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐   │
│  │  Chat API   │  Auth API   │  File API   │ Knowledge    │   │
│  │             │             │             │   API        │   │
│  └─────────────┴─────────────┴─────────────┴─────────────┘   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                   Business Logic                             │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐   │
│  │Agent Mgmt   │Tool Exec    │ Knowledge   │ Cache Mgmt   │   │
│  │             │             │ Mgmt        │             │   │
│  └─────────────┴─────────────┴─────────────┴─────────────┘   │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                    Data Storage                              │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐   │
│  │   MySQL     │    Redis    │File Storage │Vector Store │   │
│  └─────────────┴─────────────┴─────────────┴─────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
AgenticGen/
├── api/               # API Service Module
├── agent/             # Agent Management Module
├── auth/              # Authentication Module
├── cache/             # Cache Module
├── config/            # Configuration Management
├── db/                # Database Models
├── frontend/          # Frontend Interface
├── knowledge/         # Knowledge Base Module
├── tools/             # Tool Execution Module
├── deployment/        # Deployment Configuration
├── uploads/           # File Upload Directory
├── logs/              # Log Files
├── test/              # Test Files
├── requirements.txt   # Python Dependencies
└── .env.example       # Environment Variable Template
```

## Development Progress

- ✅ Core Configuration - Environment variables, database, logging, prompt management
- ✅ Database Models - Complete ORM model definitions
- ✅ Authentication - AES encryption, JWT authentication, middleware
- ✅ Cache System - Redis cache, session cache, response cache
- ✅ Agent Management - Agent factory, configuration management, OpenAI integration
- ⏳ Tool Execution Module - Python/SQL executors
- ⏳ Knowledge Base Module - Document processing and vector retrieval
- ⏳ API Service Module - FastAPI interfaces
- ⏳ Frontend Module - Web interface
- ⏳ Docker Deployment Module - Containerized deployment

## Usage Examples

### 1. Create Agent Instance

```python
from agent import AgentManager, AgentType

# Get Agent Manager
agent_manager = AgentManager()

# Create Programming Assistant Agent
agent = await agent_manager.get_or_create_agent(
    thread_id="thread_123",
    agent_type=AgentType.CODING
)

# Have a conversation
response = await agent.chat_async("Help me write a quick sort algorithm")
print(response)
```

### 2. Streaming Response

```python
# Use streaming response
async for chunk in agent.chat_stream("Explain the principle of this sorting algorithm"):
    print(chunk, end='', flush=True)
```

### 3. Knowledge Base Q&A

```python
from knowledge import KnowledgeBase

# Create knowledge base
kb = KnowledgeBase("Python Programming Guide")
await kb.add_document("python_guide.pdf")

# Search knowledge base
results = await kb.search("Python list comprehensions")
```

### 4. Execute Python Code

```python
from tools import PythonExecutor

executor = PythonExecutor()
result = await executor.execute("""
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
y = np.sin(x)
plt.plot(x, y)
plt.savefig("sine_wave.png")
print("Chart saved")
""")
print(result)
```

## API Documentation

After starting the service, visit the following addresses to view API documentation:
- Swagger UI: http://localhost:9000/docs
- ReDoc: http://localhost:9000/redoc

## Technology Stack

### Backend
- **Framework**: FastAPI
- **Database**: MySQL 5.7 + SQLAlchemy ORM
- **Cache**: Redis
- **AI Model**: OpenAI GPT API
- **Async**: asyncio + uvicorn

### Frontend
- **Foundation**: HTML5 + CSS3 + JavaScript (ES6+)
- **Communication**: Server-Sent Events (SSE)
- **UI**: Custom styles + responsive design

### Deployment
- **Container**: Docker + Docker Compose
- **Proxy**: Nginx
- **Process Manager**: Supervisor

## Key Challenges & Solutions

### 1. Large-Scale Knowledge Base Management
**Challenge**: Support for 1000+ documents and 10GB content
**Solutions**:
- Optimized chunking strategies
- Vector database
- Incremental update mechanisms

### 2. Secure Code Execution
**Challenge**: Secure Python code execution
**Solutions**:
- Docker sandbox isolation
- Resource limits
- Timeout controls

### 3. Streaming Response Performance
**Challenge**: Real-time streaming response processing
**Solutions**:
- Async IO
- Buffer optimization
- Connection pooling

### 4. Concurrent Processing
**Challenge**: High-concurrency request handling
**Solutions**:
- Async architecture
- Connection pooling
- Caching strategies

## Contributing

We welcome all forms of contributions! Please read [CONTRIBUTING.md](CONTRIBUTING.md) to learn how to participate in project development.

### Development Workflow

1. Fork this repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

Thanks to the following open-source projects for their support:
- [FastAPI](https://fastapi.tiangolo.com/) - Modern Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) - Python SQL toolkit
- [OpenAI](https://openai.com/) - Powerful AI model APIs
- [Redis](https://redis.io/) - High-performance caching database
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation library

## Contact Us

- Project Homepage: https://github.com/zcxGGmu/AgenticGen
- Issue Tracker: https://github.com/zcxGGmu/AgenticGen/issues
- Email: your-email@example.com

---

⭐ If this project helps you, please give us a star!