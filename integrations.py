import os
import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")


def get_redis_client():
    import redis
    return redis.from_url(REDIS_URL, socket_connect_timeout=2, decode_responses=True)


def cache_get(key: str):
    """Return parsed JSON value from Redis or None."""
    try:
        r = get_redis_client()
        value = r.get(key)
        if value:
            return json.loads(value)
    except Exception:
        pass
    return None


def cache_set(key: str, value, ttl: int = 60):
    """Store JSON value in Redis with TTL (seconds). Silently fails."""
    try:
        r = get_redis_client()
        r.setex(key, ttl, json.dumps(value))
    except Exception:
        pass


def cache_delete_pattern(pattern: str):
    """Delete all keys matching pattern. Silently fails."""
    try:
        r = get_redis_client()
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception:
        pass


# ─── RabbitMQ helpers ─────────────────────────────────────────────────────────

def publish_event(event_type: str, payload: dict):
    
    try:
        import pika
        params = pika.URLParameters(RABBITMQ_URL)
        params.socket_timeout = 2
        connection = pika.BlockingConnection(params)
        channel = connection.channel()
        channel.exchange_declare(exchange="todo_events", exchange_type="fanout", durable=True)
        message = json.dumps({"event": event_type, "data": payload})
        channel.basic_publish(
            exchange="todo_events",
            routing_key="",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # persistent
                content_type="application/json",
            ),
        )
        connection.close()
    except Exception:
        pass  # Never block CRUD operations


# ─── Health endpoints ─────────────────────────────────────────────────────────

@router.get("/redis/health")
def redis_health():
    try:
        r = get_redis_client()
        r.ping()
        return JSONResponse(status_code=200, content={"status": "connected", "service": "redis"})
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unavailable", "detail": str(e)})


@router.get("/rabbitmq/health")
def rabbitmq_health():
    try:
        import pika
        params = pika.URLParameters(RABBITMQ_URL)
        params.socket_timeout = 2
        connection = pika.BlockingConnection(params)
        connection.close()
        return JSONResponse(status_code=200, content={"status": "connected", "service": "rabbitmq"})
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unavailable", "detail": str(e)})
