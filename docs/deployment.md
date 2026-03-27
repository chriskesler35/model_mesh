# Deployment Guide

## Local Development

1. Copy `.env.example` to `.env`
2. Add your API keys
3. Run `docker-compose up -d`
4. Run migrations: `docker-compose exec backend alembic upgrade head`
5. Seed data: `docker-compose exec backend python -m app.scripts.seed`

## Production Deployment

### Environment Variables

Required:
- `POSTGRES_PASSWORD` - PostgreSQL password
- `REDIS_PASSWORD` - Redis password
- `ANTHROPIC_API_KEY` - Anthropic API key
- `GOOGLE_API_KEY` - Google API key
- `MODELMESH_API_KEY` - Application API key

Optional:
- `OLLAMA_BASE_URL` - Ollama server URL (default: http://localhost:11434)

### Docker Compose Production

```yaml
services:
  backend:
    environment:
      - MODELMESH_API_KEY=${MODELMESH_API_KEY}
    volumes: []  # Remove dev volume mounts
    command: uvicorn app.main:app --host 0.0.0.0 --port 18800
```

### TLS/HTTPS

Use a reverse proxy (nginx, Caddy, Traefik) to handle TLS termination.

Example nginx config:
```nginx
server {
    listen 443 ssl;
    server_name api.modelmesh.example.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://localhost:18800;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Secrets Management

- Never commit `.env` files
- Use Docker secrets or external vault for production
- Rotate API keys regularly
- Use environment-specific configuration files

## Health Checks

```bash
# Check all services
curl http://localhost:18800/health

# Expected response
{
  "status": "healthy",
  "database": "healthy",
  "redis": "healthy"
}
```

## Monitoring

- Use `docker-compose logs -f backend` to view backend logs
- Monitor PostgreSQL and Redis with standard tools
- Set up alerts for `/health` endpoint failures

## Troubleshooting

### Database connection errors
```bash
# Check PostgreSQL is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres
```

### Redis connection errors
```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli -a your_password ping
```

### Backend not starting
```bash
# Check backend logs
docker-compose logs backend

# Verify dependencies
docker-compose exec backend pip list
```