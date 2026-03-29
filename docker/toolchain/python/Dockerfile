FROM agentrelay-agent-base:latest

USER root

# Install pixi for target repo package management.
RUN curl -fsSL https://pixi.sh/install.sh | PIXI_HOME=/opt/pixi bash
ENV PATH="/opt/pixi/bin:${PATH}"

USER agent
