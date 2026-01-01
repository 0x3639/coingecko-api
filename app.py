from flask import Flask, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
from psycopg2 import pool, OperationalError
from dotenv import load_dotenv
import os
import sys
import logging

# Configure logging to stdout for Docker
logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s : %(message)s'
)
logger = logging.getLogger(__name__)

# Load .env file
load_dotenv()

# Set up a connection pool
cnxpool = None
try:
    logger.info('Creating database connection pool')
    cnxpool = pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=5,
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        port=os.getenv("DB_PORT", 5432)
    )
    logger.info('Database connection pool created successfully')
except OperationalError as e:
    logger.error(f'Failed to create database connection pool: {e}')
    raise

# Create table if it doesn't exist
try:
    db = cnxpool.getconn()
    cursor = db.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coingecko (
            id SERIAL PRIMARY KEY,
            currency_id VARCHAR(255),
            currency_value REAL,
            timestamp TIMESTAMP(6) DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.commit()
    cursor.close()
    cnxpool.putconn(db)
    logger.info('Database table verified/created successfully')
except Exception as e:
    logger.error(f'Failed to create database table: {e}')
    raise

app = Flask(__name__)

# Configure Redis for caching
app.config['CACHE_TYPE'] = 'redis'
app.config['CACHE_REDIS_URL'] = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
cache = Cache(app)

# Set up the rate limiter
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["1 per second"],
    headers_enabled=True
)

# Map full currency_id to short form
CURRENCY_MAP = {
    'zenon-2': 'znn',
    'quasar-2': 'qsr',
    'bitcoin': 'btc',
    'ethereum': 'eth'
}


@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"error": "Too Many Requests", "code": 429}), 429


@app.errorhandler(500)
def internal_error_handler(e):
    logger.error(f'Internal server error: {e}')
    return jsonify({"error": "Internal Server Error", "code": 500}), 500


@app.route("/health")
def health():
    """Health check endpoint for Docker/Kubernetes."""
    health_status = {"status": "healthy", "checks": {}}

    # Check database connection
    try:
        db = cnxpool.getconn()
        cursor = db.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        cnxpool.putconn(db)
        health_status["checks"]["database"] = "ok"
    except Exception as e:
        logger.error(f'Health check database error: {e}')
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = str(e)

    # Check Redis/cache connection
    try:
        cache.get("health_check_test")
        health_status["checks"]["cache"] = "ok"
    except Exception as e:
        logger.error(f'Health check cache error: {e}')
        health_status["status"] = "unhealthy"
        health_status["checks"]["cache"] = str(e)

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


@cache.cached(timeout=30, key_prefix='all_prices')
def get_prices():
    """Fetch latest prices from database."""
    db = None
    cursor = None

    try:
        db = cnxpool.getconn()
        cursor = db.cursor()

        query = """
            SELECT currency_id, currency_value, timestamp
            FROM coingecko
            WHERE currency_id IN ('zenon-2', 'quasar-2', 'bitcoin', 'ethereum')
            ORDER BY timestamp DESC
            LIMIT 4
        """
        cursor.execute(query)
        results = cursor.fetchall()

        if not results:
            logger.warning('No price data found in database')
            return {"error": "No data found"}

        # Convert the results to a dictionary with safe key access
        prices = {}
        for result in results:
            currency_id = result[0]
            short_code = CURRENCY_MAP.get(currency_id)
            if short_code:
                prices[short_code] = {
                    "timestamp": result[2].strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
                    "usd": result[1]
                }
            else:
                logger.warning(f'Unknown currency_id in database: {currency_id}')

        return {"data": prices}

    except OperationalError as e:
        logger.error(f'Database error in get_prices: {e}')
        return {"error": "Database connection error"}
    except Exception as e:
        logger.error(f'Unexpected error in get_prices: {e}')
        return {"error": "Internal error"}
    finally:
        if cursor:
            cursor.close()
        if db:
            cnxpool.putconn(db)


@app.route("/price")
@limiter.limit("1 per second")
def price():
    return jsonify(get_prices())


if __name__ == "__main__":
    app.run()
