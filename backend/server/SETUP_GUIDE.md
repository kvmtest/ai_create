# AI CREAT Platform - Local Setup Guide

## 📋 **Setup Overview**
- 🏠 **Local**: Python FastAPI server
- 🐳 **Docker**: PostgreSQL database + Redis + RabbitMQ + Celery worker

## 🚀 Quick Start

Prerequisites:

- Docker. Latest version.
- Python. Version 3.12.6 is recommended.

### 1. **Services Setup**

**Docker Services (Database, Redis, RabbitMQ, Worker):**

```bash
# Start Docker services
docker-compose up db redis rabbitmq worker

# Or run in background:
docker-compose up -d db redis rabbitmq worker
```

**🔍 Check Services:**
```bash
# Verify Docker services are running
docker-compose ps

# Check RabbitMQ Management UI
# http://localhost:15672 (guest/guest)
```

### 2. **Environment Setup**

In another terminal, create Python Environment and install requirements:

```bash
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

Set environment variables, (open and edit .env file). Configurations that need to be added with your own credentials:
```bash
GEMINI_API_KEY=your-api-key
STABILITY_AI_API_KEY=your-api-key
OPENAI_API_KEY=your-api-key
```

### 3. **Database Preparation**
```bash
# Run Alembic migrations
python -m alembic upgrade head
```
```bash
# Run seed script to populate initial data
python scripts/seed_complete_data.py
```

### 4. **Start Services**

**Python Server (Local):**
```bash
# Start FastAPI server locally
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 🧪 **API Testing Flow**

### **Step 1: Get Authentication Token**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "john_doe", "password": "password123"}'
```
**Response:** `{"accessToken": "eyJ..."}`

### **Step 2: Get Available Formats**
```bash
curl -X GET http://localhost:8000/api/v1/formats \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Step 3: Upload Project & Assets**

**Single File Upload:**
```bash
curl -X POST http://localhost:8000/api/v1/projects/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F 'projectName=Test Project' \
  -F 'files=@/path/to/your/image.jpg'
```

**Multiple Files Upload (Recommended):**
```bash
curl -X POST http://localhost:8000/api/v1/projects/upload \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -F 'projectName=My Design Project' \
  -F 'files=@/path/to/design.psd' \
  -F 'files=@/path/to/photo1.jpg' \
  -F 'files=@/path/to/photo2.png' \
  -F 'files=@/path/to/logo.svg'
```

**Response:**
```json
{
  "projectId": "uuid-here",
  "summary": {
    "total_files": 4,
    "successful_uploads": 4,
    "failed_uploads": 0
  }
}
```

**Note:** You can upload up to 50 files per request, with each file up to 50MB. The system will automatically:
- Process all files in parallel for faster analysis
- Use your configured AI provider (Gemini/OpenAI/Claude)
- Provide detailed upload summary with any failed files
- Handle file naming conflicts automatically

### **Step 4: Check Processing Status**
```bash
curl -X GET http://localhost:8000/api/v1/projects/{projectId}/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Step 5: Generate Assets (when status = "ready_for_review")**
```bash
curl -X POST http://localhost:8000/api/v1/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "assetIds": ["asset-uuid"],
    "formatIds": ["format-uuid"],
    "settings": {"priority": "normal"}
  }'
```

### **Step 6: Check Generation Status**
```bash
curl -X GET http://localhost:8000/api/v1/generate/{jobId}/status \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### **Step 7: Get Results (when status = "completed")**
```bash
curl -X GET http://localhost:8000/api/v1/generate/{jobId}/results \
  -H "Authorization: Bearer YOUR_TOKEN"
```

## 📊 **Database Status Check**
```bash
python scripts/db_status.py
```

## 🔍 **Health Check**
```bash
curl http://localhost:8000/health
```

## 📁 **Project Structure**
```
├── app/
│   ├── api/v1/endpoints/     # API routes
│   ├── services/             # Business logic  
│   ├── workers/              # Celery tasks
│   └── models/               # Database models
├── scripts/                  # Utility scripts
├── uploads/                  # File storage
└── alembic/                  # Database migrations
```

## ⚡ **Quick Troubleshooting**

**Database Connection Issues:**
- Check PostgreSQL is running: `pg_ctl status`
- Verify database exists: `psql -l | grep test`

**Worker Not Processing:**
- Check Docker services: `docker-compose ps`
- Check Redis: `docker-compose exec redis redis-cli ping`
- Check RabbitMQ: Visit `http://localhost:15672` (guest/guest)
- Check worker logs: `docker-compose logs worker`

**API Errors:**
- Check logs: `tail -f app.log`
- Verify JWT token not expired

## 🎯 **Testing Workflow**
1. **Auth** → Get token
2. **Formats** → See available options  
3. **Upload** → Create project + upload images
4. **Status** → Wait for "ready_for_review" 
5. **Generate** → Create repurposed assets
6. **Results** → Download generated files

**Platform is ready when you see generated files in `/uploads/{projectId}/` directory!** 🚀
