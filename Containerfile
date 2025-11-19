FROM docker.io/library/ubuntu:latest

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=en_US.UTF-8
ENV LANGUAGE=en_US:en
ENV LC_ALL=en_US.UTF-8

RUN apt-get update && \
    apt-get -y upgrade

RUN apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    screen \
    sudo \
    xrdp \
    xfce4 \
    xorgxrdp \
    dbus-x11 \
    xfce4-terminal \
    python3-pip \
    ca-certificates \
    xvfb \
    libasound2t64

RUN apt remove -y light-locker xscreensaver && \
    apt autoremove -y && \
    rm -rf /var/cache/apt /var/lib/apt/lists

WORKDIR /app/turnstile-solver
COPY . .
RUN pip3 install -r requirements.txt --break-system-packages
RUN python3 -m camoufox fetch
RUN chmod +x /app/turnstile-solver/entrypoint.sh

EXPOSE 5072
ENTRYPOINT ["/app/turnstile-solver/entrypoint.sh"]
