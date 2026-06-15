#!/usr/bin/env python3
"""
采集目录程序检查脚本 - 6个维度检查
"""
import os
import sys
import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

# 添加项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ProgramChecker:
    """程序检查器"""
    
    def __init__(self, base_path: str):
        self.base_path = Path(base_path)
        self.results = []
    
    def get_all_python_files(self) -> List[Path]:
        """获取所有Python文件"""
        files = []
        for ext in ['*.py']:
            files.extend(self.base_path.rglob(ext))
        # 排除__pycache__
        files = [f for f in files if '__pycache__' not in str(f)]
        return sorted(files)
    
    def check_syntax(self, file_path: Path) -> Tuple[bool, str]:
        """检查语法"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            ast.parse(code)
            return True, "✅ 语法正确"
        except SyntaxError as e:
            return False, f"❌ 语法错误: {e}"
        except Exception as e:
            return False, f"⚠️ 解析异常: {e}"
    
    def check_imports(self, file_path: Path) -> Tuple[bool, List[str]]:
        """检查导入语句"""
        missing = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                code = f.read()
            
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        module_name = alias.name.split('.')[0]
                        try:
                            __import__(alias.name)
                        except ImportError:
                            missing.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        try:
                            __import__(node.module)
                        except ImportError:
                            missing.append(node.module)
        except Exception as e:
            return False, [str(e)]
        
        if missing:
            return False, missing
        return True, []
    
    def check_main_function(self, file_path: Path) -> Tuple[bool, str]:
        """检查是否有main入口"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            has_main = 'if __name__' in content or 'def main(' in content
            has_argparse = 'argparse' in content or 'click' in content
            
            if has_main and has_argparse:
                return True, "✅ 有main入口 + CLI参数"
            elif has_main:
                return True, "✅ 有main入口"
            else:
                return False, "⚠️ 无可执行入口"
        except Exception as e:
            return False, str(e)
    
    def check_logging(self, file_path: Path) -> Tuple[bool, str]:
        """检查日志配置"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            has_logger_import = 'logger' in content.lower() or 'logging' in content.lower()
            has_log_statements = bool(re.search(r'logger\.(info|warning|error|debug)', content))
            
            if has_logger_import and has_log_statements:
                return True, "✅ 有日志"
            elif has_logger_import:
                return True, "✅ 有日志导入"
            else:
                return False, "⚠️ 无日志"
        except Exception as e:
            return False, str(e)
    
    def check_error_handling(self, file_path: Path) -> Tuple[bool, str]:
        """检查错误处理"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            try_blocks = len(re.findall(r'\btry\s*:', content))
            except_blocks = len(re.findall(r'\bexcept\s*:', content))
            
            if try_blocks > 0 and except_blocks > 0:
                return True, f"✅ 有{try_blocks}个try/{except_blocks}个except"
            elif try_blocks > 0:
                return False, "⚠️ 有try无except"
            else:
                return False, "⚠️ 无错误处理"
        except Exception as e:
            return False, str(e)
    
    def check_config_usage(self, file_path: Path) -> Tuple[bool, str]:
        """检查配置使用"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            uses_config = 'from utils.config import' in content or 'config.get' in content
            uses_yaml = '.yaml' in content or '.yml' in content
            
            if uses_config:
                return True, "✅ 使用config"
            elif uses_yaml:
                return True, "✅ 使用YAML配置"
            else:
                return False, "⚠️ 未使用配置管理"
        except Exception as e:
            return False, str(e)
    
    def check_file_size(self, file_path: Path) -> int:
        """获取文件大小（行数）"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return len(f.readlines())
        except:
            return 0
    
    def run_check(self) -> Dict:
        """运行所有检查"""
        files = self.get_all_python_files()
        
        print("\n" + "=" * 80)
        print("采集目录程序检查报告")
        print("=" * 80)
        
        all_results = []
        
        for file_path in files:
            relative_path = file_path.relative_to(self.base_path)
            
            # 只检查主要程序文件
            if file_path.name.startswith('_') or file_path.name == '__init__.py':
                continue
            
            print(f"\n📄 {relative_path}")
            print("-" * 60)
            
            # 1. 语法检查
            syntax_ok, syntax_msg = self.check_syntax(file_path)
            print(f"  语法: {syntax_msg}")
            
            # 2. 导入检查
            imports_ok, missing = self.check_imports(file_path)
            if imports_ok:
                print(f"  导入: ✅ 所有依赖可用")
            else:
                print(f"  导入: ⚠️ 缺失: {missing[:3]}")
            
            # 3. 入口检查
            main_ok, main_msg = self.check_main_function(file_path)
            print(f"  入口: {main_msg}")
            
            # 4. 日志检查
            log_ok, log_msg = self.check_logging(file_path)
            print(f"  日志: {log_msg}")
            
            # 5. 错误处理
            error_ok, error_msg = self.check_error_handling(file_path)
            print(f"  错误: {error_msg}")
            
            # 6. 配置管理
            config_ok, config_msg = self.check_config_usage(file_path)
            print(f"  配置: {config_msg}")
            
            # 文件大小
            lines = self.check_file_size(file_path)
            print(f"  规模: {lines} 行")
            
            # 汇总
            score = sum([syntax_ok, imports_ok, main_ok, log_ok, error_ok, config_ok])
            status = "✅ 良好" if score >= 5 else "⚠️ 待改进" if score >= 3 else "❌ 需优化"
            print(f"  综合: {status} ({score}/6)")
            
            all_results.append({
                'file': str(relative_path),
                'score': score,
                'status': status,
                'details': {
                    'syntax': syntax_ok,
                    'imports': imports_ok,
                    'main': main_ok,
                    'logging': log_ok,
                    'error': error_ok,
                    'config': config_ok
                }
            })
        
        # 汇总统计
        print("\n" + "=" * 80)
        print("汇总统计")
        print("=" * 80)
        
        total = len(all_results)
        good = sum(1 for r in all_results if r['score'] >= 5)
        need_work = sum(1 for r in all_results if 3 <= r['score'] < 5)
        need_fix = sum(1 for r in all_results if r['score'] < 3)
        
        print(f"  总文件数: {total}")
        print(f"  ✅ 良好: {good} ({good/total*100:.1f}%)")
        print(f"  ⚠️ 待改进: {need_work} ({need_work/total*100:.1f}%)")
        print(f"  ❌ 需优化: {need_fix} ({need_fix/total*100:.1f}%)")
        
        # 列出需要改进的文件
        if need_work or need_fix:
            print("\n需要改进的文件:")
            for r in sorted(all_results, key=lambda x: x['score']):
                if r['score'] < 5:
                    print(f"  [{r['score']}/6] {r['file']} - {r['status']}")
        
        print("\n" + "=" * 80)
        
        return {
            'total': total,
            'good': good,
            'need_work': need_work,
            'need_fix': need_fix,
            'details': all_results
        }


def main():
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    checker = ProgramChecker(base_path)
    checker.run_check()


if __name__ == "__main__":
    main()
