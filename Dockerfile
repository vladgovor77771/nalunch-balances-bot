FROM python:3.9.6

COPY requirements.txt .
RUN pip3 install -r requirements.txt

COPY src /app/src
COPY config.yaml /app/config.yaml

CMD ["python3", "/app/src/main.py", "--config", "/app/config.yaml"]
