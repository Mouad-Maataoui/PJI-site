#!/bin/sh

set -e


echo "Waiting for postgres..."
while ! nc -z $POSTGRES_SERVER 5432; do
  sleep 0.1
done

# Run migrations ONLY if we are the API service (optional safety check)
# Or just run it every time; Alembic is idempotent (safe to run multiple times)
if [ "$SERVICE_TYPE" = "api" ]; then
    echo "Running Alembic Migrations..."
    #alembic revision --autogenerate -m "first migration"
    #alembic upgrade head
fi

exec "$@"