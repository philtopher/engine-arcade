#!/bin/bash
# Script to run GPT Engineer with proper environment variables

# Ensure we have the right parameters
if [ $# -lt 1 ]; then
  echo "Usage: $0 <project_directory>"
  exit 1
fi

PROJECT_DIR="$1"
GPTE_DIR="/Users/ericlam/Desktop/gpt-engineer"

# Load the API key from the .env file
if [ -f "$GPTE_DIR/.env" ]; then
  source "$GPTE_DIR/.env"
fi

# Check if we have the API key
if [ -z "$OPENAI_API_KEY" ]; then
  echo "Error: OPENAI_API_KEY not found in $GPTE_DIR/.env"
  exit 1
fi

echo "Running GPT Engineer for project: $PROJECT_DIR"
cd "$GPTE_DIR" && python -m gpt_engineer.applications.cli.main "$PROJECT_DIR" --temperature 0.7 --verbose
