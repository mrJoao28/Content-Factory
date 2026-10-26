FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs npm && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY services ./services
COPY templates ./templates
RUN pip install --no-cache-dir . && npm install -g @openai/codex
ENV PYTHONPATH=/app/services/api
CMD ["python", "-m", "uvicorn", "factory.main:app", "--host", "127.0.0.1", "--port", "8000", "--no-access-log"]
