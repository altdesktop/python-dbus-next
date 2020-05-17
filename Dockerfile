FROM ubuntu:20.04

WORKDIR /app

RUN export DEBIAN_FRONTEND=noninteractive; \
    export DEBCONF_NONINTERACTIVE_SEEN=true; \
    echo 'tzdata tzdata/Areas select Etc' | debconf-set-selections; \
    echo 'tzdata tzdata/Zones/Etc select UTC' | debconf-set-selections; \
    apt update && apt install -y --no-install-recommends \
    python3-pip \
    python3 \
    libpython3.8 \
    dbus \
    virtualenv \
    python3-gi

# uncomment to test a system without gi repository
#RUN apt-get remove -y python3-gi

ARG interpreter=python3.8

COPY requirements.txt .
RUN virtualenv -p ${interpreter} env && \
    . ./env/bin/activate && \
    ./env/bin/pip install -r requirements.txt

ADD . /app

RUN find -name __pycache__ | xargs rm -r || true
CMD ["bash", "-c", ". ./env/bin/activate && dbus-run-session ./env/bin/python -m pytest"]
