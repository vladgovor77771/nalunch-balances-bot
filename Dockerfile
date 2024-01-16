FROM python:3.9.6

RUN apt-get update && \
    apt-get install -y build-essential libzbar-dev zbar-tools ffmpeg libsm6 libxext6 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY src /app/src
COPY config.yaml /app/config.yaml
