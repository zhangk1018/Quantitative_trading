"""
config.py - API配置模块

量化交易系统后端API配置管理，支持环境变量和配置文件。
"""

import os
from typing import List
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

class APISettings(BaseSettings):
    """API配置设置"""
    
    # 服务器配置
    host: str = Field(default="0.0.0.0", description="服务器监听地址")
    port: int = Field(default=8000, description="服务器监听端口")
    debug: bool = Field(default=False, description="调试模式开关")
    
    # CORS配置
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="允许的CORS源"
    )
    
    # 数据配置
    parquet_path: str = Field(
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            "data", "price", "daily", "latest_quotes.parquet"
        ),
        description="Parquet数据文件路径"
    )
    
    # 业务配置
    default_page_size: int = Field(default=50, description="默认分页大小")
    max_page_size: int = Field(default=200, description="最大分页大小")
    
    # 缓存配置
    cache_ttl: int = Field(default=300, description="缓存过期时间（秒）")
    
    # 日志配置
    log_level: str = Field(default="INFO", description="日志级别")
    log_format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="日志格式"
    )
    
    # 认证配置（单密钥门禁 + HttpOnly Cookie）
    auth_enabled: bool = Field(default=True, description="是否启用认证门禁")
    access_key: str = Field(default="", description="登录访问密钥（API_ACCESS_KEY）")
    session_secret: str = Field(default="", description="JWT 签名密钥（API_SESSION_SECRET）")
    auth_cookie_name: str = Field(default="access_token", description="会话 Cookie 名")
    auth_cookie_max_age: int = Field(default=2592000, description="会话有效期（秒，默认 30 天）")
    auth_cookie_secure: bool = Field(default=False, description="Cookie Secure 属性（生产 HTTPS 置 True）")
    
    class Config:
        env_file = ".env"
        env_prefix = "API_"
        case_sensitive = False
        extra = "ignore"  # 忽略未声明的环境变量（如 TUSHARE_TOKEN、PG_*）

# 全局配置实例
settings = APISettings()

# 配置验证
def validate_config():
    """验证配置有效性"""
    if not os.path.exists(settings.parquet_path):
        raise FileNotFoundError(
            f"Parquet数据文件不存在: {settings.parquet_path}\n"
            f"请确保数据导入脚本已运行，或设置正确的API_PARQUET_PATH环境变量"
        )
    
    if settings.debug:
        print("🔧 调试模式已启用")
        print(f"📁 数据文件: {settings.parquet_path}")
        print(f"🌐 CORS允许源: {settings.cors_origins}")
    
    return True

# 应用启动时验证配置
if __name__ == "__main__":
    try:
        validate_config()
        print("✅ 配置验证通过")
    except Exception as e:
        print(f"❌ 配置验证失败: {e}")
        exit(1)