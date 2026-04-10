#!/bin/sh
set -eu

exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind=0.0.0.0:${PORT:-8000}
