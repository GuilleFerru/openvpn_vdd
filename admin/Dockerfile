FROM python:3.11-slim

RUN pip install flask

WORKDIR /app
COPY app.py .

# Docker CLI se monta desde el host via docker-compose
# No necesitamos instalarlo aquí

CMD ["python", "app.py"]
