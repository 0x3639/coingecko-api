# CoinGecko Price API

A lightweight REST API that collects cryptocurrency prices from CoinGecko and serves them from a PostgreSQL database. Built with Flask and Celery for reliable background data collection, fully containerized with Docker.

## Features

- **Automated Price Collection**: Fetches prices every 30 seconds from CoinGecko API
- **Cached Responses**: Redis-backed caching reduces database load
- **Rate Limiting**: Protects the API with 1 request per second limit
- **Connection Pooling**: Efficient PostgreSQL connection management
- **Docker Compose**: One command to run the entire stack

## Supported Cryptocurrencies

| CoinGecko ID | Short Code |
|--------------|------------|
| bitcoin      | btc        |
| ethereum     | eth        |
| zenon-2      | znn        |
| quasar-2     | qsr        |

## API Endpoints

### GET /price

Returns the latest USD prices for all tracked cryptocurrencies.

**Response:**
```json
{
  "data": {
    "btc": {
      "usd": 43250.00,
      "timestamp": "2024-01-05T12:30:45.123456Z"
    },
    "eth": {
      "usd": 2280.50,
      "timestamp": "2024-01-05T12:30:45.123456Z"
    },
    "znn": {
      "usd": 1.25,
      "timestamp": "2024-01-05T12:30:45.123456Z"
    },
    "qsr": {
      "usd": 0.15,
      "timestamp": "2024-01-05T12:30:45.123456Z"
    }
  }
}
```

**Rate Limit Exceeded (429):**
```json
{
  "error": "Too Many Requests",
  "code": 429
}
```

## Quick Start with Docker

```bash
# Clone and start
git clone https://github.com/0x3639/coingecko-api.git
cd coingecko-api
docker compose up -d
```

The API will be available at `http://localhost:5000/price`

## Docker Services

| Service | Description | Port |
|---------|-------------|------|
| web | Flask API server | 5000 |
| worker | Celery task worker | - |
| beat | Celery scheduler | - |
| postgres | PostgreSQL 15 | 5432 |
| redis | Redis 7 | 6379 |

### Docker Commands

```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f

# Stop all services
docker compose down

# Stop and remove data volume
docker compose down -v
```

## Local Development (without Docker)

### Prerequisites

- Python 3.9+
- PostgreSQL
- Redis

### Setup

1. **Create and activate virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your database credentials
   ```

4. **Start services**
   ```bash
   # Terminal 1: Flask
   python app.py

   # Terminal 2: Celery worker
   celery -A celery_worker worker --loglevel=info

   # Terminal 3: Celery beat
   celery -A celery_worker beat --loglevel=info
   ```

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   CoinGecko     │     │     Redis       │     │   PostgreSQL    │
│      API        │     │  (Cache/Broker) │     │    Database     │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────────────────────────────────────────────────────┐
│  Docker Compose                                                 │
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Celery Beat │───▶│   Celery    │───▶│  fetch_data task    │  │
│  │ (Scheduler) │    │   Worker    │    │  (every 30 sec)     │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Flask App                            │    │
│  │  /price endpoint ──▶ Cache Check ──▶ PostgreSQL Query   │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Database Schema

The application automatically creates the required table:

```sql
CREATE TABLE coingecko (
    id SERIAL PRIMARY KEY,
    currency_id VARCHAR(255),
    currency_value REAL,
    timestamp TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP
)
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DB_HOST | localhost | PostgreSQL host |
| DB_PORT | 5432 | PostgreSQL port |
| DB_USER | coingecko | Database user |
| DB_PASSWORD | coingecko | Database password |
| DB_NAME | coingecko | Database name |
| REDIS_URL | redis://localhost:6379/0 | Redis URL for caching |
| CELERY_BROKER_URL | redis://localhost:6379/1 | Redis URL for Celery |

## License

MIT
