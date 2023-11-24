FROM python:3.9.6

RUN apt-get update && \
    apt-get install -y build-essential libzbar-dev zbar-tools ffmpeg libsm6 libxext6

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY src /app/src
COPY config.yaml /app/config.yaml
COPY photos /photos

CMD ["python3", "/app/src/main.py", "--config", "/app/config.yaml"]
