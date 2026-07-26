#!/bin/bash
# Script to link your Signal account to the signal-api container

# Check if docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker does not appear to be running"
    exit 1
fi

# Check if signal-api container exists
if ! docker ps -a --format '{{.Names}}' | grep -q "^signal-api$"; then
    echo "❌ signal-api container not found"
    echo "Please run 'docker-compose up -d' first"
    exit 1
fi

# Check if container is running
if [ "$(docker inspect -f '{{.State.Running}}' signal-api)" != "true" ]; then
    echo "⚠️  signal-api container is not running"
    read -p "Start the container now? [Y/n] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]] || [[ -z $REPLY ]]; then
        docker start signal-api
        sleep 5  # Give it time to start
    else
        exit 1
    fi
fi

# Check if we're already linked
if docker exec signal-api signal-cli -u +0 listAccounts | grep -q "already registered"; then
    echo "ℹ️  Signal account is already linked"
    echo "To relink, first run: docker exec signal-api signal-cli unlink"
    exit 0
fi

echo "📱 Linking your Signal account to the container..."
echo "Please scan the QR code with your Signal app"
echo "(Look for 'Link New Device' in Signal settings)"

echo "----------------------------------------"
docker exec -it signal-api signal-cli link -n "Virtual Coach"
echo "----------------------------------------"

# Verify the linking was successful
if docker exec signal-api signal-cli -u +0 listAccounts | grep -q "already registered"; then
    echo "✅ Successfully linked Signal account!"
    echo "You can now send and receive messages through the system"
else
    echo "❌ Failed to link Signal account"
    echo "Please try again or check the container logs:"
    echo "docker logs signal-api"
    exit 1
fi