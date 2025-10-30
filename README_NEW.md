# Healthcare AI Agentic System

Production-grade healthcare provider verification system with AI agents, trust scoring, and RAG capabilities. Built entirely with **free and open-source** tools.

## 🎯 Features

- **AI Agent Orchestration**: Meta-agent coordinates NPI lookup, geocoding, and memory storage
- **Trust Graph & TrustRank**: NetworkX PageRank algorithm computes provider trust scores
- **RAG System**: sentence-transformers + FAISS for semantic search, TinyLlama for reasoning
- **Provider Verification**: Automated workflows with evidence trails
- **Security**: JWT auth, TOTP 2FA, AES-256 encryption, SHA3 integrity hashing
- **Observability**: Prometheus metrics, structured JSON logging

## 🆓 Free OSS Stack

All components are free and open-source - no paid APIs required.

### Backend
- **FastAPI** - Modern Python web framework
- **PostgreSQL** - Relational database
- **sentence-transformers** - Text embeddings (all-MiniLM-L6-v2)
- **FAISS** - Vector similarity search
- **TinyLlama** - Local LLM for reasoning
- **NetworkX** - Graph algorithms for TrustRank

### Integrations (Free APIs)
- **CMS NPI Registry** - Public healthcare provider data
- **Nominatim/OpenStreetMap** - Free geocoding service

### Frontend
- **Next.js** - React framework
- **TailwindCSS** - Utility-first CSS

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Start all services
docker-compose up -d

# Seed admin user
docker-compose exec backend python scripts/seed_admin.py

# Run E2E demo
docker-compose exec backend bash scripts/run_e2e.sh 1003000126
```

### Manual Setup

```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Start database
docker run -d --name postgres \
  -e POSTGRES_USER=healthcare \
  -e POSTGRES_PASSWORD=healthcare123 \
  -e POSTGRES_DB=healthcare_ai \
  -p 5432:5432 postgres:15-alpine

# Seed admin
python scripts/seed_admin.py

# Start backend
uvicorn backend.main:app --reload

# Start frontend (separate terminal)
npm run dev
```

## 📋 E2E Demo

```bash
./scripts/run_e2e.sh 1003000126
```

This executes a complete workflow:
1. Creates admin user with 2FA
2. Looks up provider from NPI Registry
3. Geocodes address with Nominatim
4. Stores provider in database
5. Builds trust graph
6. Computes TrustRank scores

## 🔌 API Documentation

Access interactive API docs at: `http://localhost:8000/docs`

## 🏗️ Architecture

```
Frontend (Next.js)
        ↓
Backend API (FastAPI)
        ↓
    ┌───┴───┬───────┬──────────┐
    ↓       ↓       ↓          ↓
PostgreSQL FAISS NetworkX  External APIs
                            (NPI, OSM)
```

## 🔒 Security

- JWT + TOTP 2FA authentication
- AES-256 encryption for sensitive data
- SHA3-256 integrity hashing
- RBAC with admin/analyst/user roles

## 📊 Observability

- Prometheus metrics: `/metrics`
- Structured JSON logging
- Health checks: `/health`
- Workflow evidence trails

## 🚢 Deployment

Deploy to Vercel (frontend):
```bash
vercel deploy --prod --yes --token $VERCEL_TOKEN --name healthcare-ai
```

Deploy full stack with Docker Compose on any cloud VM.

## 📝 License

MIT License - Free to use and modify

---

Built with ❤️ using 100% free and open-source tools
