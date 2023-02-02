FROM python:3.6-alpine

# To reduce build times when developing/uploading
RUN apk add build-base && pip install websocket-client==1.3.1 dydx-v3-python==1.9.0 pyjson5==1.6.2
# Consider adding watchdog==2.2.1 if you will make a dev version

WORKDIR /app
COPY . .
# RUN pip install -r requirements.txt

# This is superceeded by the docker-compose
# CMD ["python3","-u","/app/run.py"]
