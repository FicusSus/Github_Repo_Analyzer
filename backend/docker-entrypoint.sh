#!/bin/sh
set -eu

# Apply database migrations before the API starts. Alembic takes a transaction-level lock,
# and migrations are idempotent, so restarts are safe.
alembic upgrade head

exec "$@"
