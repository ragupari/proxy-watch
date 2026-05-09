#!/bin/bash
set -e

echo "Starting ProxyMaze via Docker..."

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null
then
    echo "Docker Compose could not be found. Please install Docker and Docker Compose."
    exit 1
fi

# Determine whether to use 'docker-compose' or 'docker compose'
if command -v docker-compose &> /dev/null
then
    COMPOSE_CMD="docker-compose"
else
    COMPOSE_CMD="docker compose"
fi

echo "Building and starting containers in detached mode..."
$COMPOSE_CMD up --build -d

echo "ProxyMaze is now running!"
echo "View logs with: $COMPOSE_CMD logs -f"
