FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    git \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Install GitHub CLI.
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        | tee /etc/apt/sources.list.d/github-cli.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Install agentrelay (provides agent SDK + CLI entry points).
COPY pyproject.toml /opt/agentrelay/pyproject.toml
COPY src/ /opt/agentrelay/src/
RUN pip3 install --break-system-packages /opt/agentrelay

# Install agent git hooks (read-only for agent user).
COPY docker/hooks/pre-push /etc/agentrelay/hooks/pre-push
RUN chmod +x /etc/agentrelay/hooks/pre-push

# Non-root agent user.
RUN useradd -m -s /bin/bash agent
USER agent
RUN git config --global core.hooksPath /etc/agentrelay/hooks
WORKDIR /home/agent
