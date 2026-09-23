FROM python:3.12-slim

WORKDIR /mnt/loadtest

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["locust"]
CMD ["-f", "locustfile.py"]
