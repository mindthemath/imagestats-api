FROM python:3.11-slim-bookworm

WORKDIR /app

COPY server.py requirements.txt ./

RUN pip install -r requirements.txt

ENV PORT=8010
ENV LOG_LEVEL=INFO
ENV NUM_API_SERVERS=1
ENV WORKERS_PER_DEVICE=1
ENV AVERAGING_METHOD=arithmetic

CMD ["python", "server.py"]