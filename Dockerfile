FROM ubuntu:19.04
WORKDIR /app
RUN apt-get update && apt-get install -y dbus python3-gi python3-pip
ADD . /app
RUN pip3 install -r requirements.txt
RUN find -name __pycache__ | xargs rm -r || true
CMD ["dbus-run-session", "pytest"]
