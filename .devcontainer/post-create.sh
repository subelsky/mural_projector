#!/usr/bin/env bash
set -euo pipefail

# Install Claude using the Anthropic-recommended URL-based method
curl -fsSL https://claude.ai/install.sh | bash

# Install Gemini CLI and OpenAI Codex
#npm install -g @google/gemini-cli
#npm install -g @openai/codex

echo "Done!"
