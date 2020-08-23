FROM ubuntu:20.04

WORKDIR /app

RUN echo force-unsafe-io > /etc/dpkg/dpkg.cfg.d/docker-apt-speedup
RUN echo 'APT::Acquire::Retries "5";' > /etc/apt/apt.conf.d/80retry

RUN export DEBIAN_FRONTEND=noninteractive; \
    export DEBCONF_NONINTERACTIVE_SEEN=true; \
    echo 'tzdata tzdata/Areas select Etc' | debconf-set-selections; \
    echo 'tzdata tzdata/Zones/Etc select UTC' | debconf-set-selections; \
    apt update && \
    apt install software-properties-common -y --no-install-recommends && \
    add-apt-repository ppa:deadsnakes/ppa && \
    apt update && apt install -y --no-install-recommends \
    build-essential \
    python3-pip \
    python3 \
    python3.6 \
    python3.7 \
    python3.9 \
    python3.9-distutils \
    dbus \
    python3-gi

COPY requirements.txt .

RUN pip3 install yapf flake8 && \
    for py in python3 python3.6 python3.7 python3.9; do \
        $py -m pip install \
            pytest \
            pytest-asyncio \
            pytest-timeout \
            pytest-cov; \
    done

ADD . /app

CMD ["make", "clean", "test", "check"]
