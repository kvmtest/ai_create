# AI Provider Configuration Guide

## Quick Setup

### 1. Environment Variables

Add these to your `.env` file:

```bash
# Choose your primary AI provider
AI_PROVIDER=openai          # Options: openai, gemini, claude

# API Keys (add the ones you want to use)
OPENAI_API_KEY=your_openai_api_key_here
GEMINI_API_KEY=your_gemini_api_key_here
CLAUDE_API_KEY=your_claude_api_key_here

GEMINI_ENABLED=false
OPENAI_ENABLED=true
CLAUDE_ENABLED=false
```

### 2. Switch Providers

**Option A: Change Default Provider**
```bash
# Edit .env file
AI_PROVIDER=openai    # Switch to OpenAI
# or
AI_PROVIDER=gemini    # Switch to Gemini
```

**Option B: Force Specific Provider in API**
```bash
# Use specific provider for one request
curl -X POST /api/v1/generate \
  -H "Content-Type: application/json" \
  -d '{"projectId": "123", "ai_provider": "openai"}'
```

### 3. Restart Application
```bash
# Restart your FastAPI server
uvicorn app.main:app --reload

# Restart Celery workers
celery -A app.workers.celery_app worker --loglevel=info
```

## Provider Comparison

| Provider | Best For | Cost | Speed |
|----------|----------|------|-------|
| **OpenAI** | High accuracy, detailed analysis | High | Medium |
| **Gemini** | Fast processing, good quality | Low | Fast |
| **Claude** | Balanced performance | Medium | Medium |

## Troubleshooting

**No API responses?**
- Check your API key is valid
- Verify internet connection
- Check provider status pages

**Provider fails?**
- System automatically tries backup providers
- Check logs for specific error messages
- Ensure you have valid keys for backup providers

**Switch not working?**
- Restart the application after changing `.env`
- Clear any cached configurations
- Check logs for configuration errors

## Test Your Setup

```bash
# Quick test
curl http://localhost:8000/health

# Check AI provider status
curl http://localhost:8000/api/v1/ 
```

That's it! Your AI provider is now configured and ready to use.
