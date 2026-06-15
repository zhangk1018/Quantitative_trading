#!/usr/bin/env python3
"""配置管理模块 - 加载外置化配置"""
import os
import yaml
import re
import logging
from typing import Dict, Any

# 配置日志记录器
logger = logging.getLogger(__name__)

# 默认配置
_DEFAULT_CONFIG = {
    'data_source': {
        'name': 'baostock',
        'delay_sec': 0.3,
        'max_retries': 3,
        'timeout_sec': 30,
        'strategy': 'failover',  # failover, round_robin, weighted
        'health_check_interval': 30,  # 降低到30秒，及时发现断开
        'auto_recovery': True,
        'keep_alive_interval': 55,  # 保持连接活跃（秒），短于超时时间
        'connection_timeout': 25  # 连接超时（秒）
    },
    'minute_data': {
        'batch_days': 10,
        'max_batch_size': 2000,  # 降低批量大小，减少超时风险
        'default_cycles': ['5m', '15m', '30m', '60m'],
        'api_delay': 0.3
    },
    'indicators': {
        'ma_windows': [5, 10, 20, 60],
        'rsi_windows': [6, 12, 24],
        'macd_span': [12, 26, 9],
        'max_batch_size': 5000
    },
    'storage': {
        'type': 'postgresql',
        'batch_size': 1000
    },
    'scheduler': {
        'daily_update_time': '20:10',
        'daily_stock_list_update_time': '17:30',
        'weekly_maintenance_day': 6,
        'weekly_maintenance_time': '02:00'
    },
    'validation': {
        'price_min': 0.01,
        'price_max': 999999.99,
        'volume_min': 0,
        'volume_negative_action': 'drop',
        'ohlc_check': True,
        'volume_check': True,
        'price_range_check': True,
        'duplicate_check': True
    },
    'logging': {
        'level': 'INFO',
        'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        'max_file_size_mb': 50,
        'backup_count': 10
    },
    'backup': {
        'enabled': True,
        'backup_dir': 'data/backups',
        'max_backups': 30
    }
}

# 环境变量匹配模式
_ENV_VAR_PATTERN = re.compile(r'\$\{(\w+)\}')


def _resolve_env_vars(value):
    """递归解析配置值中的环境变量"""
    if isinstance(value, str):
        # 查找并替换环境变量
        matches = _ENV_VAR_PATTERN.findall(value)
        for var_name in matches:
            env_value = os.environ.get(var_name)
            if env_value is not None:
                value = value.replace(f'${{{var_name}}}', env_value)
            else:
                print(f"⚠️ 环境变量 {var_name} 未设置，保持原值")
        return value
    elif isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_resolve_env_vars(item) for item in value]
    else:
        return value


class Config:
    """配置类 - 提供配置访问接口"""
    
    def __init__(self, config_dict: Dict[str, Any]):
        self._config = config_dict
        self._env = os.environ.get('APP_ENV', 'dev')
    
    def __getattr__(self, name: str) -> Any:
        if name in self._config:
            return self._config[name]
        raise AttributeError(f"'Config' object has no attribute '{name}'")
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    @property
    def env(self) -> str:
        """获取当前环境"""
        return self._env
    
    def get_with_env(self, key: str, default: Any = None) -> Any:
        """按环境获取配置值（优先获取当前环境的配置）
        
        支持配置格式：
        database:
            host: default_host
            dev:
                host: dev_host
            prod:
                host: prod_host
        
        Args:
            key: 配置键（如 'database.host'）
            default: 默认值
        
        Returns:
            配置值
        """
        keys = key.split('.')
        value = self._config
        
        try:
            # 先查找非环境配置
            parent = value
            for k in keys[:-1]:
                parent = parent[k]
            
            # 如果存在环境特定配置，优先使用
            if self._env in parent and isinstance(parent[self._env], dict):
                env_config = parent[self._env]
                if keys[-1] in env_config:
                    logger.debug(f"使用环境配置 {self._env}: {key}")
                    return env_config[keys[-1]]
            
            # 使用默认配置
            return parent[keys[-1]]
        except (KeyError, TypeError):
            return default


def load_config(path: str = None, env: str = None) -> Config:
    """
    加载YAML配置文件，支持环境变量替换和多环境配置
    
    支持按环境加载不同配置文件：
    - config/pipeline.yaml (默认配置)
    - config/pipeline.dev.yaml (开发环境)
    - config/pipeline.test.yaml (测试环境)
    - config/pipeline.prod.yaml (生产环境)
    
    环境优先级（从高到低）：
    1. 命令行参数 env
    2. 环境变量 APP_ENV
    3. 默认值 'dev'
    
    Args:
        path: 配置文件路径（可选）
        env: 环境标识（可选，如 'dev', 'test', 'prod'）
    
    Returns:
        Config对象
    """
    # 确定当前环境
    if env is None:
        env = os.environ.get('APP_ENV', 'dev')
    
    # 设置环境变量
    os.environ['APP_ENV'] = env
    
    # 获取 backend 目录的绝对路径（__file__ 是 config.py，需要取父目录）
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 加载.env 文件（先后尝试 CWD 和项目根目录）
    _load_env_file()
    _load_env_file(os.path.abspath(os.path.join(backend_dir, "..", ".env")))
    
    config = _DEFAULT_CONFIG.copy()
    
    # 默认配置文件路径（使用绝对路径）
    default_paths = [
        os.path.join(backend_dir, "pipeline.yaml"),
        os.path.join(backend_dir, f"pipeline.{env}.yaml"),
        os.path.join(backend_dir, "config", "pipeline.yaml"),
        os.path.join(backend_dir, "config", f"pipeline.{env}.yaml")
    ]
    
    # 确定要加载的配置文件
    load_paths = []
    if path:
        load_paths.append(path)
    else:
        load_paths = default_paths
    
    # 按顺序加载配置文件（后续文件会覆盖前面的配置）
    for config_path in load_paths:
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    user_config = yaml.safe_load(f)
                
                # 递归合并配置
                config = _deep_merge(config, user_config)
                
                print(f"✅ 配置文件加载成功: {config_path}")
            except Exception as e:
                print(f"⚠️ 配置文件 {config_path} 加载失败: {e}")
    
    # 解析环境变量
    config = _resolve_env_vars(config)
    
    print(f"📊 当前环境: {env}")
    
    return Config(config)


def _load_env_file(env_path: str = ".env"):
    """加载.env文件中的环境变量"""
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # 跳过注释和空行
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        os.environ[key.strip()] = value.strip()
            print(f"✅ .env 文件加载成功")
        except Exception as e:
            print(f"⚠️ .env 文件加载失败: {e}")


def _deep_merge(base: Dict, update: Dict) -> Dict:
    """
    深度合并两个字典
    
    Args:
        base: 基础字典
        update: 更新字典
    
    Returns:
        合并后的字典
    """
    result = base.copy()
    
    for key, value in update.items():
        if isinstance(value, dict) and key in result and isinstance(result[key], dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


# 全局配置实例
config = load_config()


# 测试代码
if __name__ == '__main__':
    print("配置内容:")
    print(f"数据源: {config.data_source}")
    print(f"存储配置: {config.storage}")
    print(f"每日更新时间: {config.scheduler.daily_update_time}")
    print(f"校验配置: {config.validation}")