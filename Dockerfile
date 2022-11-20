FROM python:3.6-alpine

WORKDIR /app
COPY . .
RUN apk add build-base && pip install -r requirements.txt

CMD ["python3","/app/run.py"]
