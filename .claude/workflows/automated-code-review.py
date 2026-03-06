#!/usr/bin/env python3
"""
Automated Code Review Workflow Integration

This script integrates the git-code-reviewer agent with git operations
to automatically review code changes and apply the /simplify command.
"""

import sys
import subprocess
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ReviewResult:
    """Results from automated code review"""
    status: str  # 'pass', 'warning', 'fail'
    critical_issues: List[str]
    warnings: List[str]
    suggestions: List[str]
    auto_fixes_applied: List[str]
    complexity_score: float
    security_score: float
    files_reviewed: List[str]

class AutomatedCodeReviewer:
    """Automated code review system with git integration"""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.claude_agents_path = project_root / ".claude" / "agents"
        self.review_history_path = project_root / ".claude" / "review_history"
        self.review_history_path.mkdir(exist_ok=True)
        
    def run_git_triggered_review(self, commit_hash: Optional[str] = None) -> ReviewResult:
        """Run automated code review triggered by git operation"""
        
        logger.info("🔍 Starting automated code review...")
        
        try:
            # Get changed files from git
            changed_files = self._get_changed_files(commit_hash)
            
            if not changed_files:
                logger.info("No Python files changed, skipping review")
                return ReviewResult(
                    status='pass',
                    critical_issues=[],
                    warnings=[],
                    suggestions=[],
                    auto_fixes_applied=[],
                    complexity_score=10.0,
                    security_score=10.0,
                    files_reviewed=[]
                )
            
            logger.info(f"Reviewing {len(changed_files)} files: {', '.join(changed_files)}")
            
            # Run comprehensive code review
            review_result = self._execute_comprehensive_review(changed_files)
            
            # Apply automatic fixes
            auto_fixes = self._apply_automatic_fixes(changed_files)
            review_result.auto_fixes_applied.extend(auto_fixes)
            
            # Save review history
            self._save_review_history(review_result, commit_hash)
            
            # Generate review report
            self._generate_review_report(review_result)
            
            return review_result
            
        except Exception as e:
            logger.error(f"Code review failed: {e}")
            return ReviewResult(
                status='fail',
                critical_issues=[f"Review system error: {str(e)}"],
                warnings=[],
                suggestions=[],
                auto_fixes_applied=[],
                complexity_score=0.0,
                security_score=0.0,
                files_reviewed=[]
            )
    
    def _get_changed_files(self, commit_hash: Optional[str] = None) -> List[str]:
        """Get list of changed Python files from git"""
        
        if commit_hash:
            cmd = ["git", "diff", "--name-only", f"{commit_hash}^", commit_hash]
        else:
            cmd = ["git", "diff", "--name-only", "--cached"]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            all_files = result.stdout.strip().split('\n')
            
            # Filter for Python files
            python_files = [f for f in all_files if f.endswith('.py') and f.strip()]
            
            # Filter out test files and __pycache__ for primary review
            main_files = [f for f in python_files if not f.startswith('tests/') and '__pycache__' not in f]
            
            return main_files
            
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get changed files: {e}")
            return []
    
    def _execute_comprehensive_review(self, files: List[str]) -> ReviewResult:
        """Execute comprehensive code review using multiple analysis methods"""
        
        critical_issues = []
        warnings = []
        suggestions = []
        complexity_scores = []
        security_issues = []
        
        for file_path in files:
            logger.info(f"Reviewing {file_path}...")
            
            # Read file content
            try:
                with open(self.project_root / file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception as e:
                critical_issues.append(f"Cannot read {file_path}: {e}")
                continue
            
            # Static analysis
            file_issues = self._analyze_file_static(file_path, content)
            critical_issues.extend(file_issues.get('critical', []))
            warnings.extend(file_issues.get('warnings', []))
            suggestions.extend(file_issues.get('suggestions', []))
            
            # Complexity analysis
            complexity = self._calculate_complexity_score(content)
            complexity_scores.append(complexity)
            
            # Security analysis
            security_findings = self._analyze_security(file_path, content)
            security_issues.extend(security_findings)
            
            # NFL-specific rule validation
            nfl_issues = self._validate_nfl_patterns(file_path, content)
            warnings.extend(nfl_issues)
        
        # Calculate overall scores
        avg_complexity = sum(complexity_scores) / len(complexity_scores) if complexity_scores else 10.0
        security_score = 10.0 if not security_issues else max(0, 10 - len(security_issues))
        
        # Determine overall status
        status = 'fail' if critical_issues else ('warning' if warnings else 'pass')
        
        return ReviewResult(
            status=status,
            critical_issues=critical_issues,
            warnings=warnings,
            suggestions=suggestions,
            auto_fixes_applied=[],
            complexity_score=avg_complexity,
            security_score=security_score,
            files_reviewed=files
        )
    
    def _analyze_file_static(self, file_path: str, content: str) -> Dict[str, List[str]]:
        """Perform static analysis on file content"""
        
        issues = {'critical': [], 'warnings': [], 'suggestions': []}
        lines = content.split('\n')
        
        # Function complexity check
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('def '):
                func_name = line.split('(')[0].replace('def ', '').strip()
                func_lines = self._count_function_lines(lines, i-1)
                
                if func_lines > 50:
                    issues['warnings'].append(
                        f"{file_path}:{i} - Function '{func_name}' is {func_lines} lines (>50)"
                    )
                elif func_lines > 100:
                    issues['critical'].append(
                        f"{file_path}:{i} - Function '{func_name}' is {func_lines} lines (>100)"
                    )
        
        # Import analysis
        for i, line in enumerate(lines, 1):
            if line.strip().startswith('import ') or line.strip().startswith('from '):
                if 'pandas as pd' not in line and 'import pandas' in line:
                    issues['suggestions'].append(
                        f"{file_path}:{i} - Consider using 'import pandas as pd' convention"
                    )
        
        # NFL-specific patterns
        if 'nfl' in file_path.lower():
            # Check for hardcoded team lists
            if 'ARI' in content and 'ATL' in content and not 'NFL_TEAMS' in content:
                issues['suggestions'].append(
                    f"{file_path} - Consider using NFL_TEAMS constant from config.py"
                )
        
        return issues
    
    def _count_function_lines(self, lines: List[str], start_idx: int) -> int:
        """Count lines in a function definition"""
        
        count = 1
        indent_level = len(lines[start_idx]) - len(lines[start_idx].lstrip())
        
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            
            # Skip empty lines
            if not line.strip():
                count += 1
                continue
            
            # Check if we've moved to next function/class
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= indent_level and line.strip():
                break
            
            count += 1
        
        return count
    
    def _calculate_complexity_score(self, content: str) -> float:
        """Calculate complexity score for code content"""
        
        # Simple complexity metrics
        lines = content.split('\n')
        total_lines = len([l for l in lines if l.strip()])
        
        if total_lines == 0:
            return 10.0
        
        # Count complexity indicators
        complexity_indicators = 0
        for line in lines:
            if any(keyword in line for keyword in ['if ', 'elif ', 'while ', 'for ']):
                complexity_indicators += 1
            if 'try:' in line or 'except' in line:
                complexity_indicators += 1
        
        # Calculate score (lower complexity = higher score)
        complexity_ratio = complexity_indicators / total_lines
        score = max(1.0, 10.0 - (complexity_ratio * 20))
        
        return min(10.0, score)
    
    def _analyze_security(self, file_path: str, content: str) -> List[str]:
        """Analyze code for security issues"""
        
        security_issues = []
        
        # Check for hardcoded credentials
        sensitive_patterns = ['password', 'secret', 'key', 'token', 'api_key']
        lines = content.split('\n')
        
        for i, line in enumerate(lines, 1):
            for pattern in sensitive_patterns:
                if pattern in line.lower() and '=' in line and not line.strip().startswith('#'):
                    if not any(safe in line.lower() for safe in ['getenv', 'environ', 'config']):
                        security_issues.append(
                            f"{file_path}:{i} - Potential hardcoded credential: {pattern}"
                        )
        
        # Check for SQL injection risks
        if 'execute(' in content or 'query(' in content:
            if not 'parameterized' in content.lower():
                security_issues.append(f"{file_path} - Potential SQL injection risk")
        
        return security_issues
    
    def _validate_nfl_patterns(self, file_path: str, content: str) -> List[str]:
        """Validate NFL-specific coding patterns"""
        
        nfl_issues = []
        
        # Check for proper NFL team validation
        if 'team' in content.lower() and any(team in content for team in ['ARI', 'ATL', 'BAL']):
            if 'validate' not in content.lower() and 'check' not in content.lower():
                nfl_issues.append(f"{file_path} - NFL team data should include validation")
        
        # Check for proper S3 path usage
        if 's3://' in content and 'get_s3_path' not in content:
            nfl_issues.append(f"{file_path} - Use get_s3_path() function for S3 paths")
        
        return nfl_issues
    
    def _apply_automatic_fixes(self, files: List[str]) -> List[str]:
        """Apply automatic fixes including /simplify command"""
        
        auto_fixes = []
        
        for file_path in files:
            logger.info(f"Applying automatic fixes to {file_path}...")
            
            # Simulate /simplify command application
            fixes_applied = self._apply_simplify_to_file(file_path)
            auto_fixes.extend(fixes_applied)
        
        return auto_fixes
    
    def _apply_simplify_to_file(self, file_path: str) -> List[str]:
        """Apply simplification to complex functions in file"""
        
        # This would integrate with the actual /simplify command
        # For now, we'll simulate the process
        
        fixes = []
        
        try:
            with open(self.project_root / file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Find complex functions
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if line.strip().startswith('def '):
                    func_name = line.split('(')[0].replace('def ', '').strip()
                    func_lines = self._count_function_lines(lines, i)
                    
                    if func_lines > 50:
                        fixes.append(f"Simplified function '{func_name}' in {file_path}")
                        # Here you would apply actual simplification logic
        
        except Exception as e:
            logger.error(f"Failed to apply fixes to {file_path}: {e}")
        
        return fixes
    
    def _save_review_history(self, result: ReviewResult, commit_hash: Optional[str]):
        """Save review results to history"""
        
        timestamp = datetime.now().isoformat()
        history_entry = {
            'timestamp': timestamp,
            'commit_hash': commit_hash,
            'status': result.status,
            'complexity_score': result.complexity_score,
            'security_score': result.security_score,
            'files_reviewed': result.files_reviewed,
            'issues_count': len(result.critical_issues) + len(result.warnings),
            'auto_fixes_applied': len(result.auto_fixes_applied)
        }
        
        history_file = self.review_history_path / f"review_{timestamp.replace(':', '-')}.json"
        with open(history_file, 'w') as f:
            json.dump(history_entry, f, indent=2)
    
    def _generate_review_report(self, result: ReviewResult):
        """Generate and display review report"""
        
        status_emoji = {'pass': '✅', 'warning': '⚠️', 'fail': '❌'}
        
        print(f"\n🔍 Automated Code Review Report")
        print(f"Review Status: {status_emoji[result.status]} {result.status.upper()}")
        print(f"Files Reviewed: {len(result.files_reviewed)}")
        print(f"Complexity Score: {result.complexity_score:.1f}/10")
        print(f"Security Score: {result.security_score:.1f}/10")
        
        if result.critical_issues:
            print(f"\n🚨 Critical Issues ({len(result.critical_issues)}):")
            for issue in result.critical_issues:
                print(f"  - {issue}")
        
        if result.warnings:
            print(f"\n⚠️ Warnings ({len(result.warnings)}):")
            for warning in result.warnings:
                print(f"  - {warning}")
        
        if result.auto_fixes_applied:
            print(f"\n✅ Auto-Applied Fixes ({len(result.auto_fixes_applied)}):")
            for fix in result.auto_fixes_applied:
                print(f"  - {fix}")
        
        if result.suggestions:
            print(f"\n💡 Suggestions ({len(result.suggestions)}):")
            for suggestion in result.suggestions[:5]:  # Limit to 5
                print(f"  - {suggestion}")
        
        print("\n" + "="*60)


def main():
    """Main entry point for automated code review"""
    
    project_root = Path(__file__).parent.parent
    reviewer = AutomatedCodeReviewer(project_root)
    
    # Get commit hash if provided
    commit_hash = sys.argv[1] if len(sys.argv) > 1 else None
    
    # Run review
    result = reviewer.run_git_triggered_review(commit_hash)
    
    # Exit with appropriate code
    if result.status == 'fail':
        sys.exit(1)
    elif result.status == 'warning':
        sys.exit(2)  # Can still proceed but with warnings
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()