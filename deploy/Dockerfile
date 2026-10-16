# replydesk API bridge. python:3.12-slim is multi-arch (arm64 builds natively
# on the Oracle A1 host). Stdlib only — no pip install step.
FROM python:3.12-slim

WORKDIR /app
COPY replydesk/ ./replydesk/
COPY app.py ./app.py

# No .env is copied into the image; compose's env_file injects it at runtime.
EXPOSE 8010
CMD ["python", "app.py", "--serve-api", "--host", "0.0.0.0", "--port", "8010", "--env", ".env"]
