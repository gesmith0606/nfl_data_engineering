# Automated Git Code Review System

This directory contains the automated code review system that integrates with git operations to ensure code quality and apply the `/simplify` command automatically.

## 🚀 Quick Start

### Installation
```bash
# Install git hooks
chmod +x .claude/git-hooks/install-hooks.sh
./.claude/git-hooks/install-hooks.sh
```

### Test the System
```bash
# Make a test change
echo "# Test change" >> src/test_review.py

# Commit to trigger automated review
git add .
git commit -m "test: automated code review system"

# Watch the automated review in action!
```

## 📋 Components

### 1. Git-Code-Reviewer Agent
**File**: `.claude/agents/git-code-reviewer.md`

Enhanced code reviewer agent that:
- ✅ Activates automatically on git push
- ✅ Performs comprehensive code analysis  
- ✅ Applies `/simplify` command to complex functions
- ✅ Enforces NFL data engineering best practices
- ✅ Generates detailed review reports

### 2. Automated Review Script
**File**: `.claude/workflows/automated-code-review.py`

Production Python script that:
- ✅ Analyzes git diff for changed Python files
- ✅ Runs static analysis and complexity checks
- ✅ Validates NFL-specific patterns
- ✅ Applies automatic fixes via `/simplify`
- ✅ Generates comprehensive reports
- ✅ Tracks quality metrics over time

### 3. Git Hooks
**Files**: 
- `.claude/git-hooks/pre-commit` - Blocks commits with critical issues
- `.claude/git-hooks/post-commit` - Tracks quality metrics after successful commits

### 4. Installation Script
**File**: `.claude/git-hooks/install-hooks.sh`

Automated installation that:
- ✅ Copies hooks to `.git/hooks/`
- ✅ Sets proper permissions
- ✅ Creates review history directory
- ✅ Tests the installation

## 🔍 How It Works

### Pre-Commit Flow
```
git commit
    ↓
pre-commit hook triggers
    ↓
automated-code-review.py analyzes staged files
    ↓
┌─ Critical Issues Found ─→ BLOCK commit ❌
│
├─ Warnings Found ─→ Show warnings, allow commit after 5s ⚠️
│
└─ No Issues ─→ Apply /simplify, proceed with commit ✅
```

### Review Checks

#### Code Quality (Auto-fix with /simplify)
- ✅ Functions over 50 lines → break into smaller functions
- ✅ Complex nested conditions → flatten logic
- ✅ Code duplication → extract to reusable functions
- ✅ Type hints → add missing annotations

#### Security (Blocking)
- ❌ Hardcoded credentials or API keys
- ❌ SQL injection vulnerabilities  
- ❌ Insecure data handling

#### NFL Domain Rules (Project-specific)
- ⚠️ Team validation using standard 32-team list
- ⚠️ NFL business rules (downs 1-4, scores ≥0)
- ⚠️ Proper S3 path generation patterns
- ⚠️ Fantasy scoring calculation validation

#### Performance (Warning)
- ⚠️ Inefficient pandas operations
- ⚠️ Memory leaks in data processing
- ⚠️ Suboptimal S3 file operations

## 📊 Review Reports

### Example Output
```
🔍 Automated Code Review Report
Review Status: ⚠️  WARNINGS FOUND
Files Reviewed: 3
Complexity Score: 7.2/10
Security Score: 10/10

🚨 Critical Issues (0)
None found ✅

⚠️ Warnings (2)
- src/player_analytics.py:45 - Function `calculate_advanced_metrics()` is 67 lines
- src/projection_engine.py:123 - Use get_s3_path() function for S3 paths

✅ Auto-Applied Fixes (3)
- Simplified function 'calculate_advanced_metrics' in src/player_analytics.py
- Added missing type hints to src/utils.py
- Extracted duplicate NFL team validation logic

💡 Suggestions (1)
- Add return type hint for `process_injury_data()`
```

### Quality History Tracking
- **Location**: `.claude/review_history/`
- **Format**: JSON files with timestamps
- **Data**: Complexity scores, security scores, issue counts, auto-fixes applied
- **Trends**: Track code quality improvement over time

## ⚙️ Configuration

### Customizing Review Rules

#### Complexity Thresholds
Edit `automated-code-review.py`:
```python
# Function length thresholds
if func_lines > 50:  # Warning threshold
    issues['warnings'].append(...)
elif func_lines > 100:  # Critical threshold  
    issues['critical'].append(...)
```

#### NFL-Specific Rules
Add custom validation in `_validate_nfl_patterns()`:
```python
def _validate_nfl_patterns(self, file_path: str, content: str) -> List[str]:
    nfl_issues = []
    
    # Custom rule: Check for proper player position validation
    if 'position' in content and any(pos in content for pos in ['QB', 'RB', 'WR']):
        if 'FANTASY_POSITIONS' not in content:
            nfl_issues.append(f"{file_path} - Use FANTASY_POSITIONS from config.py")
    
    return nfl_issues
```

### Disabling Temporarily
```bash
# Skip review for one commit
git commit --no-verify -m "emergency fix"

# Disable hooks temporarily
mv .git/hooks/pre-commit .git/hooks/pre-commit.disabled
```

## 🎯 Integration with Development Workflow

### With Agent Framework
1. **code-implementation-specialist** - writes new code
2. **git commit** - triggers automated review
3. **Auto-apply /simplify** - improves code quality automatically
4. **code-reviewer agent** - final manual review if needed

### With Project Skills
```bash
# Use skills that may create/modify code
/ingest 2024 1 player_weekly

# Code review automatically runs on next commit
git add . && git commit -m "feat: add player weekly data"
# → Automated review analyzes changes
# → /simplify applied to any complex functions  
# → Commit proceeds if quality standards met
```

## 🔧 Troubleshooting

### Common Issues

#### "Code review script not found"
```bash
# Ensure script exists and is executable
ls -la .claude/workflows/automated-code-review.py
chmod +x .claude/workflows/automated-code-review.py
```

#### "Python3 not found"
```bash
# Check Python installation
which python3
python3 --version

# Alternative: update hooks to use specific path
# Edit .git/hooks/pre-commit line 16:
# /usr/bin/python3 "$REVIEW_SCRIPT"
```

#### "Review system error"
```bash
# Check syntax of review script
python3 -m py_compile .claude/workflows/automated-code-review.py

# View detailed error
python3 .claude/workflows/automated-code-review.py
```

### Manual Testing
```bash
# Test review script directly
python3 .claude/workflows/automated-code-review.py

# Test with specific commit
python3 .claude/workflows/automated-code-review.py abc123
```

## 🎯 Benefits

### For Individual Development
- ✅ **Automatic Quality Improvement**: `/simplify` applied to every commit
- ✅ **Consistent Standards**: Enforces project patterns automatically  
- ✅ **Early Issue Detection**: Catches problems before they reach production
- ✅ **Learning Tool**: Review feedback improves coding skills over time

### For Team Collaboration  
- ✅ **Uniform Code Quality**: All team members follow same standards
- ✅ **Reduced Review Burden**: Automated checks handle routine issues
- ✅ **Historical Tracking**: Quality metrics track team improvement
- ✅ **NFL Domain Expertise**: Project-specific rules embedded in reviews

### For NFL Data Pipeline
- ✅ **Data Quality Assurance**: Validates NFL business rules automatically
- ✅ **Performance Optimization**: Catches inefficient data processing patterns
- ✅ **Security Compliance**: Prevents credential exposure in sports data code
- ✅ **S3 Best Practices**: Enforces proper cloud storage patterns

This automated code review system ensures that every change to your NFL data engineering project meets production-quality standards while automatically improving code complexity through the `/simplify` command.