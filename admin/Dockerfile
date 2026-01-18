FROM python:3.11-slim

RUN pip install flask

WORKDIR /app

# Copy application files
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Docker CLI is mounted from host via docker-compose

CMD ["python", "app.py"]
