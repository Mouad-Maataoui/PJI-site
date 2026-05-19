#!/bin/bash

#### REQUIREMENTS
## Python 3.11 used with `python3.11` cmd.
## A venv with pip installed
## A .env file containing the needed variables specified in the documentation
####
source .env

## Python
pip install -r requirements.txt

## Postgresql
sudo apt install postgresql -y
sudo systemctl start postgresql
sudo -u postgres createdb \"$POSTGRES_DB\"
sudo -i -u postgres psql -c "CREATE USER \"$POSTGRES_USER\" WITH ENCRYPTED PASSWORD '$POSTGRES_PASSWORD';"
sudo -i -u postgres psql -c "ALTER DATABASE \"$POSTGRES_DB\" OWNER TO \"$POSTGRES_USER\";"
sudo -i -u postgres psql -c "ALTER SCHEMA public OWNER TO \"$POSTGRES_USER\";"
sudo -i -u postgres psql -c "GRANT USAGE, CREATE ON SCHEMA public TO \"$POSTGRES_USER\";"
sudo -i -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE \"$POSTGRES_DB\" TO \"$POSTGRES_USER\";"
alembic revision --autogenerate -m "first migration"
alembic upgrade head


## Redis
sudo apt install redis-server -y
sudo systemctl start redis

