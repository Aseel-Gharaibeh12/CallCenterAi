# Al-Mustaqbal voice assistant - runs on any Linux server with Docker
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# git is needed to install Pipecat from GitHub
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 7860
CMD ["python", "bot.py", "--host", "0.0.0.0", "--port", "7860"]
