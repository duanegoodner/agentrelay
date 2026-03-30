FROM agentrelay-agent-python:latest

# Install Claude Code via native installer (self-contained binary, no npm needed).
USER agent
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && chmod a+rx /home/agent \
    && chmod -R a+rX /home/agent/.local/
ENV PATH="/home/agent/.local/bin:${PATH}"

# Helper script: seed Claude Code folder trust for the container workdir.
# Must COPY as root since /usr/local/bin is root-owned.
USER root
COPY docker/framework/claude-code/trust-workdir.py /usr/local/bin/claude-trust-workdir
RUN chmod +x /usr/local/bin/claude-trust-workdir

# Pre-seed Claude Code config to suppress first-run interactive prompts.
# Without this, every ephemeral container triggers onboarding dialogs that
# consume the orchestrator's kickoff prompt sent via tmux send-keys.
# - ~/.claude.json: marks onboarding complete (skips theme picker, API key
#   confirmation, security notes). Folder trust is seeded at runtime by
#   claude-trust-workdir since the worktree path is not known at build time.
# - ~/.claude/settings.json: skips the --dangerously-skip-permissions warning.
# - ~/.claude/statsig.json: prevents statsig initialization network request.
USER agent
RUN mkdir -p /home/agent/.claude \
    && echo '{"skipDangerousModePermissionPrompt":true,"apiKeyHelper":"echo $_ANTHROPIC_API_KEY"}' > /home/agent/.claude/settings.json \
    && echo '{}' > /home/agent/.claude/statsig.json \
    && echo '{"hasCompletedOnboarding":true,"numStartups":1}' > /home/agent/.claude.json
