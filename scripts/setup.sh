#!/bin/bash

# ============================================
# ITSM Knowledge-Based Multi-Agent Setup
# ============================================

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
cat << "EOF"
╔═══════════════════════════════════════════════════════════════╗
║                                                               ║
║   ITSM Knowledge-Based Multi-Agent Solution                  ║
║   Setup Script                                               ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
EOF
echo -e "${NC}"

# Check prerequisites
echo -e "${BLUE}📋 Checking prerequisites...${NC}"

if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 is not installed${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python 3 found: $(python3 --version)${NC}"

if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}⚠ Docker not found (optional for local dev)${NC}"
else
    echo -e "${GREEN}✓ Docker found: $(docker --version)${NC}"
fi

if ! command -v az &> /dev/null; then
    echo -e "${YELLOW}⚠ Azure CLI not found (required for deployment)${NC}"
else
    echo -e "${GREEN}✓ Azure CLI found: $(az --version | head -n 1)${NC}"
fi

echo ""

# Create virtual environment
echo -e "${BLUE}🐍 Setting up Python virtual environment...${NC}"

if [ -d "venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment already exists${NC}"
    read -p "Recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf venv
        echo -e "${BLUE}Creating new virtual environment...${NC}"
        python3 -m venv venv
    fi
else
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
fi

echo ""

# Activate virtual environment
echo -e "${BLUE}🔌 Activating virtual environment...${NC}"
source venv/bin/activate || . venv/Scripts/activate || {
    echo -e "${RED}✗ Failed to activate virtual environment${NC}"
    exit 1
}
echo -e "${GREEN}✓ Virtual environment activated${NC}"

echo ""

# Upgrade pip
echo -e "${BLUE}⬆️  Upgrading pip...${NC}"
pip install --upgrade pip --quiet
echo -e "${GREEN}✓ pip upgraded${NC}"

echo ""

# Install dependencies
echo -e "${BLUE}📦 Installing dependencies...${NC}"
echo -e "${YELLOW}This may take a few minutes...${NC}"

pip install -r requirements.txt --quiet

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ Dependencies installed successfully${NC}"
else
    echo -e "${RED}✗ Failed to install dependencies${NC}"
    exit 1
fi

echo ""

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo -e "${BLUE}📝 Creating .env file from template...${NC}"
    cp .env.example .env
    echo -e "${GREEN}✓ .env file created${NC}"
    echo -e "${YELLOW}⚠ IMPORTANT: Please update .env with your Azure credentials!${NC}"
else
    echo -e "${YELLOW}⚠ .env file already exists (not overwriting)${NC}"
fi

echo ""

# Check Docker services
if command -v docker &> /dev/null; then
    echo -e "${BLUE}🐳 Checking Docker setup...${NC}"
    
    if docker-compose version &> /dev/null || docker compose version &> /dev/null; then
        echo -e "${GREEN}✓ Docker Compose available${NC}"
        echo -e "${YELLOW}💡 You can start APIs with: docker-compose up -d${NC}"
    else
        echo -e "${YELLOW}⚠ Docker Compose not found${NC}"
    fi
fi

echo ""

# Summary
echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                               ║${NC}"
echo -e "${GREEN}║  ✅  Setup completed successfully!                            ║${NC}"
echo -e "${GREEN}║                                                               ║${NC}"
echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"

echo ""
echo -e "${YELLOW}📋 Next Steps:${NC}"
echo ""
echo -e "  ${BLUE}1.${NC} Update your .env file with Azure credentials:"
echo -e "     ${YELLOW}nano .env${NC}"
echo ""
echo -e "  ${BLUE}2.${NC} Update .env with GCC Azure OpenAI and AI Search values"
echo -e "     - AZURE_OPENAI_ENDPOINT / DEPLOYMENT / API_VERSION"
echo -e "     - AZURE_SEARCH_ENDPOINT / AZURE_SEARCH_INDEX"
echo ""
echo -e "  ${BLUE}3.${NC} Start the FastAPI services:"
echo -e "     ${YELLOW}docker-compose up -d${NC}"
echo ""
echo -e "  ${BLUE}4.${NC} Verify APIs are running:"
echo -e "     ${YELLOW}curl http://localhost:8000/${NC}"
echo -e "     ${YELLOW}curl http://localhost:8001/${NC}"
echo ""
echo -e "  ${BLUE}5.${NC} Run the orchestrator:"
echo -e "     ${YELLOW}source venv/bin/activate${NC}"
echo -e "     ${YELLOW}python src/main.py --help${NC}"
echo ""
echo -e "${GREEN}📚 For detailed instructions, see QUICKSTART.md${NC}"
echo ""
