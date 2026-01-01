# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Flask API that fetches cryptocurrency prices from CoinGecko and stores them in PostgreSQL. Uses Celery with Redis for scheduled background tasks. Fully containerized with Docker Compose.

## Commands

### Docker (recommended)
```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop services
docker compose down

# Rebuild after code changes
docker compose up -d --build
```

### Local Development
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run Flask
python app.py

# Run Celery worker
celery -A celery_worker worker --loglevel=info

# Run Celery beat
celery -A celery_worker beat --loglevel=info
```

## Architecture

**app.py** - Flask application with a single `/price` endpoint
- Uses PostgreSQL connection pooling via `psycopg2.pool.ThreadedConnectionPool`
- Redis-backed caching (30-second TTL) via Flask-Caching
- Rate limiting (1 req/sec) via Flask-Limiter
- Returns prices for ZNN, QSR, BTC, ETH

**tasks.py** - Celery task definitions and configuration
- Configures Celery beat schedule (30-second intervals)
- `fetch_data` task queries CoinGecko API and inserts prices into PostgreSQL
- Uses Redis as message broker

**celery_worker.py** - Entry point for Celery worker

**docker-compose.yml** - Defines 5 services: postgres, redis, web, worker, beat

## Environment Variables

See `.env.example` for defaults. Key variables:
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `REDIS_URL` - Redis URL for caching
- `CELERY_BROKER_URL` - Redis URL for Celery broker
