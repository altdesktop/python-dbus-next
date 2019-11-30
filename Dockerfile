FROM ubuntu:19.04

WORKDIR /app

RUN apt-get update && apt-get install -y \
    python3-pip \
    python3.8 \
    virtualenv \
    python3-gi

# uncomment to test a system without gi repository
#RUN apt-get remove -y python3-gi

ARG interpreter=python3.7

COPY requirements.txt .
RUN virtualenv -p ${interpreter} env && \
    . env/bin/activate && \
    pip3 install -r requirements.txt

ADD . /app

RUN find -name __pycache__ | xargs rm -r || true
CMD ["bash", "-c", "source env/bin/activate && dbus-run-session python -m pytest"]
