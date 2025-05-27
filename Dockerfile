FROM python:3.12.10-alpine3.21

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

ENV PORT=8010
ENV LOG_LEVEL=INFO
ENV NUM_API_SERVERS=1
ENV WORKERS_PER_DEVICE=1
ENV AVERAGING_METHOD=arithmetic

COPY server.py .
CMD ["python", "server.py"]