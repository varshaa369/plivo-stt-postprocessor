#!/bin/bash
# Quick setup script to apply STT post-processor optimizations

echo "========================================="
echo "STT Post-Processor Optimization Setup"
echo "========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in the right directory
if [ ! -f "score.sh" ]; then
    echo -e "${RED}Error: score.sh not found. Please run this from your project root.${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Backing up original files...${NC}"
cp src/ranker_onnx.py src/ranker_onnx.py.backup
cp src/rules.py src/rules.py.backup
echo -e "${GREEN}✓ Backups created${NC}"
echo ""

echo -e "${YELLOW}Step 2: Please provide the optimized files...${NC}"
echo "Copy the optimized files to:"
echo "  - src/ranker_onnx.py"
echo "  - src/rules.py"
echo ""
read -p "Press Enter when files are in place..."
echo ""

echo -e "${YELLOW}Step 3: Quick latency test (10 runs)...${NC}"
python measure_latency.py --onnx models/distilbert-base-uncased.int8.onnx --runs 10 --warmup 2
echo ""

read -p "Does latency look good (p95 < 100ms)? (y/n): " latency_ok
if [ "$latency_ok" != "y" ]; then
    echo -e "${RED}Latency still too high. Check the OPTIMIZATION_GUIDE.md for troubleshooting.${NC}"
    exit 1
fi

echo ""
echo -e "${YELLOW}Step 4: Running full pipeline (export + run + eval + latency)...${NC}"
bash score.sh
echo ""

echo -e "${GREEN}========================================="
echo "Setup Complete!"
echo "=========================================${NC}"
echo ""
echo "Next steps:"
echo "1. Review the metrics above"
echo "2. If metrics are good, record your Loom video"
echo "3. Key points to cover in video:"
echo "   - Show the before/after metrics"
echo "   - Explain batch masking optimization"
echo "   - Explain email/text normalization rules"
echo "   - Demo the <30ms latency"
echo ""
echo "To restore original files:"
echo "  cp src/ranker_onnx.py.backup src/ranker_onnx.py"
echo "  cp src/rules.py.backup src/rules.py"
