FROM mcr.microsoft.com/devcontainers/python:3.14

# Install basic development tools and Lua toolchain
RUN apt-get clean && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      vim \
      lua5.4 \
      luarocks \
      unzip

# Install luacheck (Lua linter)
RUN luarocks install luacheck

# Install lua-language-server
ARG LUA_LS_VERSION=3.17.1
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then ARCH_SUFFIX="arm64"; else ARCH_SUFFIX="x64"; fi && \
    curl -fsSL -o /tmp/lua-ls.tar.gz \
      "https://github.com/LuaLS/lua-language-server/releases/download/${LUA_LS_VERSION}/lua-language-server-${LUA_LS_VERSION}-linux-${ARCH_SUFFIX}.tar.gz" && \
    mkdir -p /usr/local/lib/lua-language-server && \
    tar -xzf /tmp/lua-ls.tar.gz -C /usr/local/lib/lua-language-server && \
    ln -sf /usr/local/lib/lua-language-server/bin/lua-language-server /usr/local/bin/lua-language-server && \
    rm /tmp/lua-ls.tar.gz

# Install StyLua (Lua formatter)
ARG STYLUA_VERSION=2.4.0
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then ARCH_SUFFIX="aarch64"; else ARCH_SUFFIX="x86_64"; fi && \
    curl -fsSL -o /tmp/stylua.zip \
      "https://github.com/JohnnyMorganz/StyLua/releases/download/v${STYLUA_VERSION}/stylua-linux-${ARCH_SUFFIX}.zip" && \
    unzip -o /tmp/stylua.zip -d /usr/local/bin/ && \
    chmod +x /usr/local/bin/stylua && \
    rm /tmp/stylua.zip

RUN apt-get clean && rm -rf /var/lib/apt/lists/*

ENV DEVCONTAINER=true
