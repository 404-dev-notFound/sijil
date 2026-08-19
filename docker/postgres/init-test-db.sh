#!/bin/bash
# Runs automatically on first container init (docker-entrypoint-initdb.d convention) —
# creates the separate database integration tests run against, so they never touch the
# main dev database. Already applied manually to the running dev volume; this covers
# fresh clones / `docker compose down -v` resets.
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE DATABASE sijil_test;
EOSQL
