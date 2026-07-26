# Virtual Run Coach

A local-first coaching system for marathon training with data sovereignty, using Signal for communication and Obsidian for data storage.

## Architecture

The system runs in Docker containers with three main components:

1. **Signal API**: Handles messaging via Signal protocol
2. **Sync Agent**: Fetches workout data from Garmin/Hevy/Strava and stores as Markdown
3. **Coach Orchestrator**: AI-powered coaching logic using Gemini API

## Prerequisites

- Docker and Docker Compose
- Signal account
- API keys for:
  - Gemini (or Anthropic)
  - Garmin/Strava/Hevy (depending on data sources)

## Setup

### 1. Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your actual values:

```env
GEMINI_API_KEY=your_gemini_api_key
MY_PHONE_NUMBER=+1234567890
GARMIN_EMAIL=your@email.com
GARMIN_PASSWORD=yourpassword
HEVY_API_KEY=your_hevy_key
```

### 2. Signal Setup

1. Start the containers:
   ```bash
   docker-compose up -d
   ```

2. Link your Signal account:
   ```bash
   ./scripts/link_signal.sh
   ```
   
   This helper script will:
   - Check Docker and container status
   - Start the container if needed
   - Guide you through the QR code linking process
   - Verify the connection was successful

3. Follow the QR code instructions to link your device:
   - Open Signal on your phone
   - Go to Settings > Linked Devices
   - Tap "Link New Device" and scan the QR code

### 3. Data Sync

The sync agent will automatically:
- Pull workout data from connected services
- Store as Markdown files in `./obsidian-vault`
- Make data available to the coaching AI

## Usage

### Basic Commands

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f [service]

# Restart a specific service
docker-compose restart coach-orchestrator

# Stop all services
docker-compose down
```

### Testing

Run test scripts directly on your host or within containers:

#### On Host Machine
```bash
# Test Gemini integration
python orchestrator/tests/test_gemini.py

# Test Garmin sync
python sync-agent/tests/test_garmin.py
```

#### Within Docker Containers
```bash
# Run Gemini tests in orchestrator container
docker exec -it coach-orchestrator python tests/test_gemini.py

# Run Garmin tests in sync-agent container
docker exec -it sync-agent python tests/test_garmin.py

# For development with automatic restart on changes:
docker-compose up --build --force-recreate orchestrator
```

## Development

### Project Structure

```
.
├── docker-compose.yml    # Main configuration
├── .env                  # Environment variables
├── obsidian-vault/       # Workout data storage
├── orchestrator/         # AI coaching logic
│   ├── main.py           # Main orchestrator code
│   ├── tests/            # Test scripts
│   └── Dockerfile
├── sync-agent/           # Data sync services
│   ├── sync_workouts.py  # Main sync logic
│   ├── tests/            # Test scripts
│   └── Dockerfile
└── signal-data/          # Signal configuration
```

### Adding New Data Sources

1. Create a new sync script in `sync-agent/`
2. Add required environment variables to `.env.example`
3. Update the Dockerfile to include new dependencies
4. Add the sync logic to the main sync workflow

## Troubleshooting

### Common Issues

1. **Signal connection problems**:
   - Verify QR code scanning was successful
   - Check `docker logs signal-api`
   - Ensure port 8088 is available

2. **API key errors**:
   - Double-check all values in `.env`
   - Verify the services can reach external APIs

3. **Permission issues**:
   - Ensure proper ownership of `signal-data/` and `obsidian-vault/`
   - Run `chmod -R 777 signal-data obsidian-vault` if needed

### Debugging Commands

```bash
# Check running containers
docker ps

# View container logs
docker logs [container_name]

# Enter a container for debugging
docker exec -it [container_name] bash

# Test Signal API directly
curl -X POST http://localhost:8088/v1/send \
  -H "Content-Type: application/json" \
  -d '{"number":"+1234567890","message":"Test message"}'
```

## License

MIT - Use at your own risk. This is personal project code.

## Roadmap

- [x] Basic Signal integration
- [x] Workout data sync
- [x] Gemini coaching logic
- [ ] Advanced training analysis
- [ ] Web interface for configuration
- [ ] Mobile app companion