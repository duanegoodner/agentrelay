FROM agentrelay-agent-python:latest

# Install Claude Code via native installer (self-contained binary, no npm needed).
USER agent
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && chmod a+rx /home/agent \
    && chmod -R a+rX /home/agent/.local/
ENV PATH="/home/agent/.local/bin:${PATH}"
