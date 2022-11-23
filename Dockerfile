FROM python:3.6-alpine

RUN apk add build-base

WORKDIR /app
COPY . .
RUN pip install -r requirements.txt

CMD ["python3","-u","/app/run.py"]
