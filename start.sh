#!/bin/bash

# Exit on any error
set -e

# Define colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}=======================================${NC}"
echo -e "${BLUE}  Starting Orion World State Engine    ${NC}"
echo -e "${BLUE}=======================================${NC}"

echo -e "${YELLOW}Building and starting Docker containers...${NC}"
docker compose up --build -d

echo -e "${GREEN}Containers started successfully!${NC}"
echo -e ""
echo -e "Services are available at:"
echo -e "  Frontend:    ${BLUE}http://localhost:5173${NC}"
echo -e "  Backend API: ${BLUE}http://localhost:8000${NC}"
echo -e ""
echo -e "To view logs, run: ${YELLOW}docker compose logs -f${NC}"
echo -e "To stop services, run: ${YELLOW}docker compose down${NC}"
