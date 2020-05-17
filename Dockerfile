FROM ubuntu:20.04

WORKDIR /app

RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-apt-speedup
RUN echo 'APT::Acquire::Retries "5";' > /etc/apt/apt.conf.d/80retry

RUN export DEBIAN_FRONTEND=noninteractive; \
    export DEBCONF_NONINTERACTIVE_SEEN=true; \
    echo 'tzdata tzdata/Areas select Etc' | debconf-set-selections; \
    echo 'tzdata tzdata/Zones/Etc select UTC' | debconf-set-selections; \
    apt update && apt install -y --no-install-recommends \
    build-essential \
    python3-pip \
    python3 \
    libpython3.8 \
    dbus \
    virtualenv \
    python3-gi

# uncomment to test a system without gi repository
#RUN apt-get remove -y python3-gi

COPY requirements.txt .

RUN pip3 install -r requirements.txt

ADD . /app

RUN find -name __pycache__ | xargs rm -r || true

CMD ["make", "test", "check"]
