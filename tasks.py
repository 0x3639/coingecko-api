from celery import Celery
from celery.schedules import timedelta
import requests
from requests.exceptions import RequestException
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
logger.info('Setting up database connection pool')
try:
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

app = Celery('tasks', broker=os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1'))

# Schedule the fetch_data task to run every 30 seconds
app.conf.beat_schedule = {
    'fetch-every-30-seconds': {
        'task': 'tasks.fetch_data',
        'schedule': timedelta(seconds=30),
    },
}

COINGECKO_API_URL = 'https://api.coingecko.com/api/v3/simple/price'
COINGECKO_PARAMS = 'ids=zenon-2,bitcoin,quasar-2,ethereum&vs_currencies=usd'
REQUEST_TIMEOUT = 10  # seconds


@app.task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_data(self):
    """Fetch cryptocurrency prices from CoinGecko and store in database."""
    db = None
    cursor = None

    try:
        # Get database connection
        logger.debug('Getting connection from pool')
        db = cnxpool.getconn()
        cursor = db.cursor()

        # Query the CoinGecko API
        logger.info('Fetching data from CoinGecko API')
        try:
            response = requests.get(
                f'{COINGECKO_API_URL}?{COINGECKO_PARAMS}',
                timeout=REQUEST_TIMEOUT
            )
        except RequestException as e:
            logger.error(f'HTTP request failed: {e}')
            raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

        # Check HTTP status code
        if response.status_code != 200:
            logger.error(f'CoinGecko API returned status {response.status_code}: {response.text[:200]}')
            if response.status_code in (429, 500, 502, 503, 504):
                # Retryable errors
                raise self.retry(countdown=60 * (2 ** self.request.retries))
            return  # Non-retryable error, skip this run

        # Parse JSON response
        try:
            data = response.json()
        except ValueError as e:
            logger.error(f'Failed to parse JSON response: {e}')
            raise self.retry(exc=e, countdown=60)

        # Check for API error response
        if 'status' in data and 'error_code' in data.get('status', {}):
            error_code = data['status'].get('error_code')
            error_msg = data['status'].get('error_message', 'Unknown error')
            logger.error(f'CoinGecko API error {error_code}: {error_msg}')
            if error_code == 429:
                raise self.retry(countdown=120)
            return

        # Validate response structure
        if not isinstance(data, dict) or not data:
            logger.error(f'Unexpected API response format: {type(data)}')
            return

        # Insert each currency into the database
        logger.info('Inserting data into the database')
        inserted_count = 0
        for currency_id, currency_data in data.items():
            if not isinstance(currency_data, dict):
                logger.warning(f'Skipping {currency_id}: invalid data format')
                continue

            usd_value = currency_data.get('usd')
            if usd_value is None:
                logger.warning(f'Skipping {currency_id}: no USD value found')
                continue

            try:
                cursor.execute("""
                    INSERT INTO coingecko (currency_id, currency_value)
                    VALUES (%s, %s)
                """, (currency_id, usd_value))
                inserted_count += 1
            except Exception as e:
                logger.error(f'Failed to insert {currency_id}: {e}')
                continue

        db.commit()
        logger.info(f'Successfully inserted {inserted_count} price records')

    except self.MaxRetriesExceededError:
        logger.error('Max retries exceeded for fetch_data task')
        raise
    except Exception as e:
        logger.error(f'Unexpected error in fetch_data: {e}')
        raise
    finally:
        # Always return connection to pool
        if cursor:
            cursor.close()
        if db:
            cnxpool.putconn(db)
            logger.debug('Database connection returned to pool')
