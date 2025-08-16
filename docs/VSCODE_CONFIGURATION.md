# VS Code Configuration Documentation

**Date Created:** August 15, 2025  
**Purpose:** Document VS Code settings for NFL Data Engineering project  
**Location:** Global settings + Workspace settings

---

## 📁 **Configuration Files Overview**

### **Global Settings** (`~/.vscode/settings.json`)
**Purpose:** Personal VS Code preferences that work across all projects

### **Workspace Settings** (`.vscode/settings.json`)  
**Purpose:** NFL project-specific configurations that apply only to this project

---

## 🤖 **AI Assistant Configuration**

### **GitHub Copilot Integration**
```json
"github.copilot.nextEditSuggestions.enabled": true,
"github.copilot.enable": {
    "*": true,
    "python": true,
    "markdown": true,
    "json": true
}
```
**Purpose:** Enable GitHub Copilot for inline code suggestions and autocompletion across relevant file types.

### **Roo Code Integration** 
```json
"experimentalFeatures": {
    "enableGitHubCopilotConnection": true
},
"providers": {
    "githubCopilot": {
        "models": {
            "claude": {
                "modelId": "claude-3-7-sonnet-20250219",
                "priority": 1
            }
        }
    }
}
```
**Purpose:** Configure Roo Code to use GitHub Copilot's infrastructure with Claude 3.7 Sonnet model. This provides:
- **No separate API key required** - uses existing GitHub Copilot subscription
- **Conversational AI assistance** for complex reasoning and architecture decisions
- **NFL domain expertise** for business logic and data validation
- **Complementary to Copilot** - Roo handles complex tasks, Copilot handles quick suggestions

---

## 🐍 **Python Development Configuration**

### **Environment Management**
```json
"python.defaultInterpreterPath": "./venv/bin/python",
"python.terminal.activateEnvironment": true,
"python.analysis.typeCheckingMode": "basic"
```
**Purpose:** 
- Automatically use project virtual environment (`./venv/`)
- Auto-activate venv when opening terminals
- Enable basic type checking for better code quality

### **Project-Specific Python Path** (Workspace)
```json
"terminal.integrated.env.osx": {
    "PYTHONPATH": "${workspaceFolder}/src",
    "AWS_DEFAULT_REGION": "us-east-2"
}
```
**Purpose:**
- Allow imports from `src/` directory (e.g., `from nfl_data_integration import NFLDataFetcher`)
- Set AWS region for S3 operations to match project buckets

---

## 📊 **Data Engineering Optimizations**

### **File Associations**
```json
"files.associations": {
    "*.parquet": "text",
    "*.env": "properties", 
    "*.md": "markdown"
}
```
**Purpose:** Proper syntax highlighting for data engineering file types.

### **Jupyter Integration**
```json
"jupyter.askForKernelRestart": false,
"jupyter.interactiveWindow.textEditor.executeSelection": true,
"jupyter.notebookFileRoot": "${workspaceFolder}"
```
**Purpose:** Streamlined notebook development for Silver layer analysis and data exploration.

---

## 🔧 **Project Workflow Optimizations**

### **Git Integration**
```json
"git.confirmSync": false,
"git.enableSmartCommit": true,
"git.autofetch": true
```
**Purpose:** Smooth Git workflow for iterative data pipeline development.

### **Editor Preferences**
```json
"editor.wordWrap": "on",
"editor.formatOnSave": true,
"explorer.confirmDelete": false
```
**Purpose:** Reduce friction during development, especially for long data processing scripts.

---

## 🎯 **NFL Project-Specific Context** (Workspace)

### **Roo Context Files**
```json
"roo-cline.contextFiles": [
    "copilot-instructions.md",
    "development_tasks.md", 
    "README.md",
    "src/nfl_data_integration.py"
]
```
**Purpose:** Automatically provide Roo with key project documentation and code examples for context-aware assistance.

### **Recommended Extensions**
```json
"extensions.recommendations": [
    "ms-python.python",
    "ms-toolsai.jupyter", 
    "rooveterinaryinc.roo-cline",
    "github.copilot"
]
```
**Purpose:** Ensure team members get the same extension setup for consistent development experience.

---

## 🚀 **Benefits of This Configuration**

### **For NFL Data Engineering:**
- **AI-Enhanced Development:** Both inline suggestions (Copilot) and complex reasoning (Roo)
- **Seamless Python Workflow:** Automatic venv activation, proper imports from `src/`
- **AWS Integration:** Environment variables set for S3 operations
- **Data Science Ready:** Jupyter notebooks, Parquet file support

### **For Team Collaboration:**
- **Consistent Environment:** Workspace settings ensure same setup across developers
- **Context-Aware AI:** Roo automatically understands project structure and goals
- **Documented Decisions:** This file explains why each setting was chosen

---

## 📋 **Maintenance Notes**

### **When to Update:**
- **New AI Models:** Update Claude model ID when newer versions available
- **Team Changes:** Add new recommended extensions as project needs grow
- **Environment Changes:** Update Python paths or AWS regions if infrastructure changes

### **Current Version Info:**
- **Claude Model:** claude-3-7-sonnet-20250219 (via GitHub Copilot)
- **Python Version:** 3.9+ (NFL data pipeline requirement)
- **AWS Region:** us-east-2 (matches S3 bucket configuration)

---

**This configuration optimizes VS Code for NFL data engineering development with dual AI assistance and seamless project workflows.**
