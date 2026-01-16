FROM python:3.11-slim

RUN pip install flask pexpect

WORKDIR /app
COPY app.py .

# Instalar Docker CLI para ejecutar comandos
RUN apt-get update && apt-get install -y docker.io && rm -rf /var/lib/apt/lists/*

CMD ["python", "app.py"]
