FROM mcr.microsoft.com/devcontainers/python:3.14

# Install basic development tools and iptables/ipset
RUN apt-get clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      vim

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

ENV DEVCONTAINER=true
