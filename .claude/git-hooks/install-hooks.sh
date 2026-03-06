#!/bin/bash
#
# Install Git Hooks for Automated Code Review
#
# This script installs the git hooks that activate the
# automated code review system on git operations.

set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🔧 Installing Git Hooks for Automated Code Review...${NC}"

# Get project root directory
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null)

if [ -z "$PROJECT_ROOT" ]; then
    echo -e "${RED}❌ Error: Not in a git repository${NC}"
    exit 1
fi

echo -e "${YELLOW}📂 Project root: $PROJECT_ROOT${NC}"

# Paths
HOOKS_SOURCE_DIR="$PROJECT_ROOT/.claude/git-hooks"
HOOKS_TARGET_DIR="$PROJECT_ROOT/.git/hooks"
WORKFLOWS_DIR="$PROJECT_ROOT/.claude/workflows"
REVIEW_HISTORY_DIR="$PROJECT_ROOT/.claude/review_history"

# Check if source hooks exist
if [ ! -d "$HOOKS_SOURCE_DIR" ]; then
    echo -e "${RED}❌ Error: Hooks source directory not found: $HOOKS_SOURCE_DIR${NC}"
    exit 1
fi

# Create necessary directories
echo -e "${YELLOW}📁 Creating directories...${NC}"
mkdir -p "$HOOKS_TARGET_DIR"
mkdir -p "$WORKFLOWS_DIR"
mkdir -p "$REVIEW_HISTORY_DIR"

# Install pre-commit hook
echo -e "${YELLOW}🪝 Installing pre-commit hook...${NC}"
if [ -f "$HOOKS_SOURCE_DIR/pre-commit" ]; then
    cp "$HOOKS_SOURCE_DIR/pre-commit" "$HOOKS_TARGET_DIR/pre-commit"
    chmod +x "$HOOKS_TARGET_DIR/pre-commit"
    echo -e "${GREEN}✅ Pre-commit hook installed${NC}"
else
    echo -e "${RED}❌ Warning: pre-commit hook not found${NC}"
fi

# Install post-commit hook
echo -e "${YELLOW}🪝 Installing post-commit hook...${NC}"
if [ -f "$HOOKS_SOURCE_DIR/post-commit" ]; then
    cp "$HOOKS_SOURCE_DIR/post-commit" "$HOOKS_TARGET_DIR/post-commit"
    chmod +x "$HOOKS_TARGET_DIR/post-commit"
    echo -e "${GREEN}✅ Post-commit hook installed${NC}"
else
    echo -e "${RED}❌ Warning: post-commit hook not found${NC}"
fi

# Make workflow script executable
REVIEW_SCRIPT="$WORKFLOWS_DIR/automated-code-review.py"
if [ -f "$REVIEW_SCRIPT" ]; then
    chmod +x "$REVIEW_SCRIPT"
    echo -e "${GREEN}✅ Code review script made executable${NC}"
else
    echo -e "${RED}❌ Warning: Code review script not found: $REVIEW_SCRIPT${NC}"
fi

# Create .gitignore entry for review history
GITIGNORE_FILE="$PROJECT_ROOT/.gitignore"
REVIEW_HISTORY_ENTRY=".claude/review_history/"

if [ -f "$GITIGNORE_FILE" ]; then
    if ! grep -q "$REVIEW_HISTORY_ENTRY" "$GITIGNORE_FILE"; then
        echo "" >> "$GITIGNORE_FILE"
        echo "# Automated code review history" >> "$GITIGNORE_FILE"
        echo "$REVIEW_HISTORY_ENTRY" >> "$GITIGNORE_FILE"
        echo -e "${GREEN}✅ Added review history to .gitignore${NC}"
    else
        echo -e "${YELLOW}⚠️  Review history already in .gitignore${NC}"
    fi
fi

# Test the installation
echo -e "${YELLOW}🧪 Testing hook installation...${NC}"

# Check if hooks are executable
if [ -x "$HOOKS_TARGET_DIR/pre-commit" ]; then
    echo -e "${GREEN}✅ Pre-commit hook is executable${NC}"
else
    echo -e "${RED}❌ Pre-commit hook is not executable${NC}"
fi

if [ -x "$HOOKS_TARGET_DIR/post-commit" ]; then
    echo -e "${GREEN}✅ Post-commit hook is executable${NC}"
else
    echo -e "${RED}❌ Post-commit hook is not executable${NC}"
fi

# Check Python environment
if command -v python3 >/dev/null 2>&1; then
    echo -e "${GREEN}✅ Python3 is available${NC}"
else
    echo -e "${RED}❌ Warning: Python3 not found in PATH${NC}"
fi

# Test the review script
if [ -f "$REVIEW_SCRIPT" ] && python3 -m py_compile "$REVIEW_SCRIPT" 2>/dev/null; then
    echo -e "${GREEN}✅ Code review script syntax is valid${NC}"
else
    echo -e "${RED}❌ Warning: Code review script has syntax errors${NC}"
fi

echo ""
echo -e "${GREEN}🎉 Git hooks installation completed!${NC}"
echo ""
echo -e "${YELLOW}📋 What happens now:${NC}"
echo "   • Every 'git commit' will trigger automated code review"
echo "   • Code review results will be saved to .claude/review_history/"
echo "   • Critical issues will block commits"
echo "   • Warnings will allow commits with a delay"
echo "   • The /simplify command will be applied automatically"
echo ""
echo -e "${YELLOW}🚀 To test the system:${NC}"
echo "   1. Make a small change to a Python file"
echo "   2. Run: git add . && git commit -m 'test: automated review'"
echo "   3. Watch the automated code review in action!"
echo ""
echo -e "${YELLOW}⚙️  To disable temporarily:${NC}"
echo "   Use: git commit --no-verify"
echo ""
echo -e "${YELLOW}🔧 To uninstall:${NC}"
echo "   Remove files from .git/hooks/ directory"