#!/bin/bash
# Step 1: Create base project structure

echo "Step 1: Creating project structure..."

# Create main project directory
mkdir -p itsm-knowledge-multiagent
cd itsm-knowledge-multiagent

# Create all subdirectories
mkdir -p src/agents/config
mkdir -p src/tools
mkdir -p src/api/ivanti
mkdir -p src/api/nice_incontact
mkdir -p src/core
mkdir -p tests/unit
mkdir -p tests/integration
mkdir -p docs
mkdir -p scripts
mkdir -p knowledge-bases/itsm
mkdir -p knowledge-bases/investigation

# Create __init__.py files for Python packages
touch src/__init__.py
touch src/agents/__init__.py
touch src/agents/config/__init__.py
touch src/tools/__init__.py
touch src/api/__init__.py
touch src/api/ivanti/__init__.py
touch src/api/nice_incontact/__init__.py
touch src/core/__init__.py
touch tests/__init__.py
touch tests/unit/__init__.py
touch tests/integration/__init__.py

echo "✓ Project structure created!"
echo ""
echo "Your structure:"
tree -L 3 || find . -type d | sed 's|[^/]*/| |g'