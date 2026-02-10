# ARM / macOS Build Instructions

## Build steps

1. Download dependencies:
   ```bash
   uv run download_deps.py
   ```

2. Build deps image:
   ```bash
   docker build -f Dockerfile.deps -t infiniflow/ragflow_deps .
   ```

3. Build main image (slim):
   ```bash
   docker build --build-arg LIGHTEN=1 -f Dockerfile -t infiniflow/ragflow:nightly-slim .
   ```

4. Configure `docker/.env` (set PostgreSQL credentials, LLM endpoints, etc.)

5. Run:
   ```bash
   cd docker
   docker compose -f docker-compose-macos.yml up -d
   ```
