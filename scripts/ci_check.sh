#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# PraxiAlpha — Local CI Check
#
# Runs the same lint, format, type, and test checks that GitHub
# Actions runs. Use this BEFORE pushing to catch failures early.
#
# Usage:
#   ./scripts/ci_check.sh          # run all checks (lint + format + types + tests)
#   ./scripts/ci_check.sh --fix    # auto-fix lint + format issues, then run tests
# ─────────────────────────────────────────────────────────────

set -euo pipefail  # Strict mode for setup, disabled below for check accumulation

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FIX_MODE=false
if [[ "${1:-}" == "--fix" ]]; then
    FIX_MODE=true
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🔍 PraxiAlpha — Local CI Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

FAILED=0

# Disable exit-on-error so we can accumulate failures
set +e

# ── Step 1: Ruff Lint ──
echo -n "  [1/4] Ruff lint ........... "
if $FIX_MODE; then
    python3 -m ruff check backend/ scripts/ --fix --quiet 2>/dev/null
    echo -e "${GREEN}fixed ✅${NC}"
else
    if python3 -m ruff check backend/ scripts/ --quiet 2>/dev/null; then
        echo -e "${GREEN}passed ✅${NC}"
    else
        echo -e "${RED}FAILED ❌${NC}"
        echo ""
        python3 -m ruff check backend/ scripts/
        FAILED=1
    fi
fi

# ── Step 2: Ruff Format ──
echo -n "  [2/4] Ruff format ........ "
if $FIX_MODE; then
    python3 -m ruff format backend/ scripts/ --quiet 2>/dev/null
    echo -e "${GREEN}fixed ✅${NC}"
else
    if python3 -m ruff format --check backend/ scripts/ --quiet 2>/dev/null; then
        echo -e "${GREEN}passed ✅${NC}"
    else
        echo -e "${RED}FAILED ❌${NC}"
        echo ""
        python3 -m ruff format --check backend/ scripts/
        FAILED=1
    fi
fi

# ── Step 3: Mypy ──
echo -n "  [3/4] Mypy types ......... "
if python3 -m mypy backend/ --ignore-missing-imports --no-error-summary 2>/dev/null | grep -q "error"; then
    echo -e "${RED}FAILED ❌${NC}"
    echo ""
    python3 -m mypy backend/ --ignore-missing-imports
    FAILED=1
else
    echo -e "${GREEN}passed ✅${NC}"
fi

# ── Step 4: Pytest ──
echo -n "  [4/4] Pytest ............. "
if python3 -m pytest --tb=short -q 2>/dev/null; then
    echo -e "${GREEN}passed ✅${NC}"
else
    echo -e "${RED}FAILED ❌${NC}"
    echo ""
    python3 -m pytest --tb=short
    FAILED=1
fi

# Re-enable strict mode for the exit
set -e

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [[ $FAILED -eq 0 ]]; then
    echo -e "  ${GREEN}All checks passed — safe to push! 🚀${NC}"
else
    echo -e "  ${RED}CI checks failed — fix before pushing! 🛑${NC}"
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

exit $FAILED
