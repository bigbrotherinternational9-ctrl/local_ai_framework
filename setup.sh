#!/bin/bash

# MEDUSA Framework Setup Script

echo "Installing MEDUSA Framework dependencies..."
pip install -r requirements.txt

echo ""
echo "Optional: Install Flask for dashboard"
pip install Flask==3.0.3

echo ""
echo "Setup complete!"
echo ""
echo "Usage:"
echo "  python medusa_integrated.py --mode app       # Run AI loop with MEDUSA review"
echo "  python medusa_integrated.py --mode console   # Run review console"
echo "  python medusa_integrated.py --mode dashboard # Run web dashboard"
echo ""
echo "Make sure Ollama is running: ollama pull qwen2.5:7b"
