FROM ubuntu:19.04

WORKDIR /app

RUN apt-get update && apt-get install -y python3-pip

# uncomment to test a system without gi repository
#RUN apt-get remove -y python3-gi

COPY requirements.txt .
RUN pip3 install -r requirements.txt

ADD . /app

RUN find -name __pycache__ | xargs rm -r || true
CMD ["dbus-run-session", "pytest"]
