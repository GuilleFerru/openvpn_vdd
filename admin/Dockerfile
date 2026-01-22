FROM python:3.11-slim

RUN pip install flask

WORKDIR /app

# Copy application files
COPY app.py .
COPY templates/ templates/
COPY static/ static/

# Install Docker CLI
RUN apt-get update && apt-get install -y curl && \
    curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-24.0.7.tgz | tar zxvf - --strip-components 1 -C /usr/bin docker/docker && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Docker socket is mounted from host via docker-compose

CMD ["python", "app.py"]
