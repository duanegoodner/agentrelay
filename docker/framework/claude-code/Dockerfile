FROM agentrelay-agent-python:latest

# Install Claude Code via native installer (self-contained binary, no npm needed).
USER agent
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && chmod a+rx /home/agent \
    && chmod -R a+rX /home/agent/.local/
ENV PATH="/home/agent/.local/bin:${PATH}"

# Helper scripts (must COPY as root since /usr/local/bin is root-owned).
USER root
COPY docker/framework/claude-code/trust-workdir.py /usr/local/bin/claude-trust-workdir
RUN chmod +x /usr/local/bin/claude-trust-workdir
COPY docker/framework/claude-code/setup-credentials.py /usr/local/bin/claude-setup-credentials
RUN chmod +x /usr/local/bin/claude-setup-credentials

# Pre-seed Claude Code config to suppress first-run interactive prompts.
# Without this, every ephemeral container triggers onboarding dialogs that
# consume the orchestrator's kickoff prompt sent via tmux send-keys.
# - ~/.claude.json: marks onboarding complete (skips theme picker, API key
#   confirmation, security notes). Folder trust is seeded at runtime by
#   claude-trust-workdir since the worktree path is not known at build time.
# - ~/.claude/settings.json: generated at runtime by claude-setup-credentials
#   (API key mode includes apiKeyHelper; OAuth mode omits it).
# - ~/.claude/statsig.json: prevents statsig initialization network request.
USER agent
RUN mkdir -p /home/agent/.claude \
    && echo '{}' > /home/agent/.claude/statsig.json \
    && echo '{"hasCompletedOnboarding":true,"numStartups":1}' > /home/agent/.claude.json
