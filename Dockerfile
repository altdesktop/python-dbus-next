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
    python3.7 \
    python3.7-distutils \
    python3.9 \
    python3.9-distutils \
    python3.10 \
    python3.10-distutils \
    curl \
    dbus \
    python3-gi

RUN set -e -x; \
    pip3 install 'yapf==0.31' 'flake8==4.0.1'; \
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py; \
    for py in python3.7 python3.8 python3.9 python3.10; do \
        ${py} get-pip.py; \
        PYTHONPATH=/usr/lib/${py}/site-packages ${py} -m pip install \
            'pytest==6.2.5' \
            'pytest-asyncio==0.16.0' \
            'pytest-timeout==2.0.2' \
            'pytest-cov==3.0.0'; \
    done

ADD . /app

CMD ["make", "clean", "test", "check"]
