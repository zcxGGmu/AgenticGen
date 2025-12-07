# AgenticGen - AI Programming Assistant

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

**[简体中文](README_zh.md) | English**

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

#### Quick Start

```bash
# Clone the repository
git clone https://github.com/zcxGGmu/AgenticGen.git
cd AgenticGen

# Start all services with one command
./scripts/start.sh

# Or manually with docker-compose
cp deployment/.env.example .env
# Edit .env file to configure your OpenAI API key
docker-compose -f deployment/docker-compose.yml up -d
```

#### Management Commands

```bash
# Start services
./scripts/start.sh

# Stop services
./scripts/start.sh stop

# Restart services
./scripts/start.sh restart

# View logs
./scripts/start.sh logs

# View real-time logs
./scripts/start.sh logs -f

# Rebuild images
./scripts/start.sh build

# Clean all resources
./scripts/start.sh cleanup
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
│   ├── main.py        # FastAPI application entry point
│   ├── routes/        # API routes
│   └── __init__.py    # API module initialization
├── agent/             # Agent Management Module
│   ├── agent_manager.py # Agent lifecycle management
│   ├── agent_factory.py # Agent creation factory
│   ├── base_agent.py  # Base agent class
│   ├── agents/        # Specific agent implementations
│   └── __init__.py    # Agent module initialization
├── auth/              # Authentication Module
│   ├── auth.py        # Authentication logic
│   ├── middleware.py  # Auth middleware
│   └── __init__.py    # Auth module initialization
├── cache/             # Cache Module
│   ├── cache.py       # Redis cache implementation
│   └── __init__.py    # Cache module initialization
├── config/            # Configuration Management
│   ├── config.py      # Pydantic settings
│   ├── __init__.py    # Config module initialization
│   └── prompts.py     # Prompt templates
├── db/                # Database Models
│   ├── models.py      # SQLAlchemy models
│   ├── connection.py  # Database connection
│   └── __init__.py    # DB module initialization
├── frontend/          # Frontend Interface
│   ├── index.html     # Main HTML page
│   ├── css/           # Stylesheets
│   ├── js/            # JavaScript files
│   └── assets/        # Static assets
├── knowledge/         # Knowledge Base Module
│   ├── knowledge_base.py # KB implementation
│   ├── document_processor.py # Document processing
│   ├── vector_store.py # Vector storage
│   └── __init__.py    # Knowledge module initialization
├── tools/             # Tool Execution Module
│   ├── python_executor.py # Python code executor
│   ├── sql_executor.py # SQL executor
│   ├── tools.py       # Tool definitions
│   └── __init__.py    # Tools module initialization
├── deployment/        # Deployment Configuration
│   ├── docker-compose.yml # Docker Compose config
│   ├── Dockerfile     # Docker image build
│   ├── nginx.conf     # Nginx proxy config
│   ├── init.sql       # Database initialization
│   └── .env.example   # Environment variables template
├── scripts/           # Utility scripts
│   └── start.sh       # Startup script
├── uploads/           # File Upload Directory
├── logs/              # Log Files
├── data/              # Application Data
├── requirements.txt   # Python Dependencies
└── .env.example       # Environment Variable Template
```

## Development Progress

- ✅ Core Configuration - Environment variables, database, logging, prompt management
- ✅ Database Models - Complete ORM model definitions
- ✅ Authentication - AES encryption, JWT authentication, middleware
- ✅ Cache System - Redis cache, session cache, response cache
- ✅ Agent Management - Agent factory, configuration management, OpenAI integration
- ✅ Tool Execution Module - Secure Python/SQL executors with sandbox support
- ✅ Knowledge Base Module - Document processing, embeddings, and RAG retrieval
- ✅ API Service Module - Complete FastAPI interfaces with SSE support
- ✅ Frontend Module - Responsive web interface with real-time chat
- ✅ Docker Deployment Module - Production-ready containerized deployment

**Status: 🎉 Project Complete! All 10 modules have been implemented and integrated.**

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

### Backend Technologies
- **Framework**: FastAPI 0.104+ - Modern, fast web framework for building APIs
- **Database**: MySQL 5.7+ with SQLAlchemy ORM - Robust relational database
- **Cache**: Redis 6.0+ - High-performance in-memory data store
- **AI Model**: OpenAI GPT API - Advanced language model capabilities
- **Async Runtime**: asyncio + uvicorn - High-concurrency server
- **Authentication**: JWT + AES encryption - Secure authentication system

### Frontend Technologies
- **Foundation**: HTML5 + CSS3 + JavaScript (ES6+) - Modern web standards
- **Communication**: Server-Sent Events (SSE) - Real-time updates
- **UI Framework**: Custom CSS with responsive design - Mobile-friendly interface
- **Features**: Dark mode, multi-language support, file upload

### Deployment & Infrastructure
- **Containerization**: Docker + Docker Compose - Consistent deployment environment
- **Reverse Proxy**: Nginx - Load balancing and SSL termination
- **Database Migration**: Alembic - Database version control
- **Vector Storage**: FAISS + NumPy - Efficient similarity search
- **Document Processing**: PyPDF2, python-docx - Multi-format support

### Security Features
- **Code Execution Sandbox**: Docker isolation for safe code execution
- **API Key Management**: Secure key generation and validation
- **CORS Protection**: Cross-origin request security
- **Input Validation**: Comprehensive data sanitization

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