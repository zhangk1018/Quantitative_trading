#!/usr/bin/env python3
"""告警规则引擎 - 支持动态告警基线和YAML模板化规则"""
import re
from typing import Dict, Any, Optional
from utils.logger import setup_logger
from utils.config import config

logger = setup_logger('alert_engine')


class AlertLevel:
    """告警级别枚举"""
    CRITICAL = 'critical'
    WARNING = 'warning'
    INFO = 'info'


class AlertEngine:
    """告警规则引擎 - 根据标的类型匹配动态阈值"""
    
    def __init__(self):
        self.rules = config.alert.get('rules', {})
        self.default_thresholds = config.alert.get('threshold', {})
        self.levels = config.alert.get('levels', {})
    
    def match_rule(self, symbol: str, is_st: bool = False) -> Optional[str]:
        """
        根据股票代码匹配告警规则
        
        Args:
            symbol: 股票代码
            is_st: 是否为ST股票
        
        Returns:
            匹配的规则名称，None表示未匹配任何规则
        """
        for rule_name, rule_config in self.rules.items():
            pattern = rule_config.get('pattern', '')
            requires_st_tag = rule_config.get('requires_st_tag', False)
            
            # 检查ST标记要求
            if requires_st_tag and not is_st:
                continue
            
            # 检查代码模式匹配
            if pattern and re.match(pattern, symbol):
                return rule_name
        
        return None
    
    def get_thresholds(self, symbol: str, is_st: bool = False) -> Dict[str, float]:
        """
        获取指定标的的告警阈值
        
        Args:
            symbol: 股票代码
            is_st: 是否为ST股票
        
        Returns:
            阈值字典
        """
        rule_name = self.match_rule(symbol, is_st)
        
        if rule_name and rule_name in self.rules:
            thresholds = self.rules[rule_name].get('thresholds', {})
            logger.debug(f"股票 {symbol} 匹配规则 {rule_name}，使用自定义阈值")
            return thresholds
        
        logger.debug(f"股票 {symbol} 未匹配规则，使用默认阈值")
        return self.default_thresholds
    
    def evaluate(self, symbol: str, metric_type: str, value: float, 
                 is_st: bool = False) -> Optional[Dict[str, Any]]:
        """
        评估指标是否触发告警
        
        Args:
            symbol: 股票代码
            metric_type: 指标类型 (fail_rate, empty_data_ratio, latency_threshold_sec)
            value: 指标值
            is_st: 是否为ST股票
        
        Returns:
            告警信息字典，如果未触发告警则返回None
        """
        thresholds = self.get_thresholds(symbol, is_st)
        threshold_value = thresholds.get(metric_type)
        
        if threshold_value is None:
            logger.debug(f"未知指标类型: {metric_type}")
            return None
        
        # 判断是否超过阈值
        exceeded = False
        if metric_type == 'latency_threshold_sec':
            exceeded = value > threshold_value
        else:
            exceeded = value > threshold_value
        
        if exceeded:
            severity = self._calculate_severity(value, threshold_value)
            level = self._get_alert_level(severity)
            
            alert_info = {
                'symbol': symbol,
                'metric_type': metric_type,
                'current_value': value,
                'threshold': threshold_value,
                'severity': severity,
                'level': level,
                'channels': self._get_notify_channels(level),
                'rule_name': self.match_rule(symbol, is_st) or 'default'
            }
            
            logger.warning(f"🚨 告警触发: {symbol} {metric_type}={value} > {threshold_value} (级别: {level}, 严重度: {severity})")
            return alert_info
        
        return None
    
    def _calculate_severity(self, current_value: float, threshold: float) -> float:
        """
        计算告警严重度
        
        Args:
            current_value: 当前值
            threshold: 阈值
        
        Returns:
            严重度 (0.0-1.0)
        """
        ratio = current_value / threshold
        
        if ratio >= 2.0:
            return 1.0
        elif ratio >= 1.5:
            return 0.8
        elif ratio >= 1.2:
            return 0.6
        elif ratio >= 1.0:
            return 0.4
        else:
            return 0.0
    
    def _get_alert_level(self, severity: float) -> str:
        """
        根据严重度获取告警级别
        
        Args:
            severity: 严重度 (0.0-1.0)
        
        Returns:
            告警级别
        """
        for level_name, level_config in self.levels.items():
            min_severity = level_config.get('min_severity', 0.0)
            if severity >= min_severity:
                return level_name
        
        return AlertLevel.INFO
    
    def _get_notify_channels(self, level: str) -> list:
        """
        获取告警通知渠道
        
        Args:
            level: 告警级别
        
        Returns:
            通知渠道列表
        """
        level_config = self.levels.get(level, {})
        return level_config.get('notify_channels', ['log'])
    
    def evaluate_batch(self, metrics: Dict[str, Dict[str, float]], 
                       is_st_map: Dict[str, bool] = None) -> list:
        """
        批量评估多个标的的指标
        
        Args:
            metrics: 指标字典 {symbol: {metric_type: value}}
            is_st_map: ST标记字典 {symbol: is_st}
        
        Returns:
            告警信息列表
        """
        alerts = []
        
        for symbol, metric_dict in metrics.items():
            is_st = is_st_map.get(symbol, False) if is_st_map else False
            
            for metric_type, value in metric_dict.items():
                alert = self.evaluate(symbol, metric_type, value, is_st)
                if alert:
                    alerts.append(alert)
        
        return alerts
    
    def get_rule_info(self, symbol: str, is_st: bool = False) -> Dict[str, Any]:
        """
        获取标的匹配的规则信息
        
        Args:
            symbol: 股票代码
            is_st: 是否为ST股票
        
        Returns:
            规则信息字典
        """
        rule_name = self.match_rule(symbol, is_st)
        thresholds = self.get_thresholds(symbol, is_st)
        
        return {
            'symbol': symbol,
            'is_st': is_st,
            'matched_rule': rule_name,
            'thresholds': thresholds
        }


# 测试函数
if __name__ == '__main__':
    engine = AlertEngine()
    
    # 测试不同类型股票的阈值匹配
    test_symbols = [
        'sh.510050',  # ETF
        'sh.600000',  # 大盘股
        'sh.603000',  # 中小盘股
        'sh.600800',  # 普通股票（未匹配特殊规则）
    ]
    
    print("测试告警规则匹配:")
    for symbol in test_symbols:
        info = engine.get_rule_info(symbol)
        print(f"  {symbol}:")
        print(f"    匹配规则: {info['matched_rule']}")
        print(f"    阈值: {info['thresholds']}")
        print()
    
    # 测试告警评估
    print("\n测试告警评估:")
    metrics = {
        'sh.510050': {'fail_rate': 0.06},  # ETF，超过0.05阈值
        'sh.600000': {'fail_rate': 0.07},  # 大盘股，未超过0.08阈值
        'sh.603000': {'latency_threshold_sec': 400},  # 中小盘股，超过360阈值
    }
    
    alerts = engine.evaluate_batch(metrics)
    for alert in alerts:
        print(f"  🚨 {alert['symbol']} {alert['metric_type']}={alert['current_value']}")
        print(f"     阈值: {alert['threshold']}, 级别: {alert['level']}, 严重度: {alert['severity']}")
