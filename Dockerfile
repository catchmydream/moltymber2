FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir flask==3.0.0

COPY . .

RUN mkdir -p logs data && chmod +x start.sh

# Expose dashboard port
EXPOSE 8080

# Jalankan bot + dashboard sekaligus
CMD ["bash", "start.sh"]
