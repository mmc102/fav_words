#!/bin/bash

set -e

echo "Building and starting Docker containers..."
docker-compose up --build -d

echo "Containers are running:"
docker ps

echo "Your Word Lookup app is accessible
