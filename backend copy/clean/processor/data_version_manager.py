#!/usr/bin/env python3
"""数据版本管理模块 - 实现数据版本管理与快照机制"""
import os
import json
import shutil
import hashlib
from datetime import datetime
from typing import Optional, List, Dict, Any
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger('data_version_manager')


class DataVersionManager:
    """
    数据版本管理器 - 实现数据版本管理与快照机制
    
    功能：
    - 数据版本记录与追踪
    - 定期快照机制
    - 版本回滚支持
    - 数据血缘追踪
    """
    
    def __init__(self, storage_path: str = None):
        """
        Args:
            storage_path: 版本数据存储路径，默认在项目根目录下的 data/version 目录
        """
        if storage_path is None:
            # 项目根目录
            root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.storage_path = os.path.join(root_path, 'data', 'version')
        else:
            self.storage_path = storage_path
        
        # 确保目录存在
        os.makedirs(self.storage_path, exist_ok=True)
        
        # 版本记录文件
        self.version_file = os.path.join(self.storage_path, 'versions.json')
        self.snapshot_dir = os.path.join(self.storage_path, 'snapshots')
        os.makedirs(self.snapshot_dir, exist_ok=True)
        
        # 加载版本记录
        self.versions = self._load_versions()
    
    def _load_versions(self) -> List[Dict[str, Any]]:
        """加载版本记录"""
        if os.path.exists(self.version_file):
            try:
                with open(self.version_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"加载版本记录失败: {str(e)}")
                return []
        return []
    
    def _save_versions(self):
        """保存版本记录"""
        with open(self.version_file, 'w', encoding='utf-8') as f:
            json.dump(self.versions, f, ensure_ascii=False, indent=2)
    
    def _generate_version_id(self) -> str:
        """生成版本ID（时间戳+随机数）"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"v{timestamp}"
    
    def _calculate_hash(self, data: pd.DataFrame) -> str:
        """计算数据哈希值（用于数据完整性校验）"""
        try:
            # 将DataFrame转换为字符串并计算MD5
            data_str = data.to_csv(index=False)
            return hashlib.md5(data_str.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.warning(f"计算数据哈希失败: {str(e)}")
            return ""
    
    def create_version(
        self,
        data_type: str,
        data: pd.DataFrame,
        description: str = "",
        tags: Optional[List[str]] = None
    ) -> str:
        """
        创建数据版本
        
        Args:
            data_type: 数据类型（如 'quotes', 'indicators', 'financial', 'stock_list'）
            data: 数据内容
            description: 版本描述
            tags: 版本标签列表
        
        Returns:
            版本ID
        """
        version_id = self._generate_version_id()
        
        # 创建版本记录
        version_record = {
            'version_id': version_id,
            'data_type': data_type,
            'description': description,
            'tags': tags or [],
            'created_at': datetime.now().isoformat(),
            'row_count': len(data),
            'hash': self._calculate_hash(data),
            'snapshot_path': None,
            'metadata': {}
        }
        
        # 保存快照
        snapshot_path = self._save_snapshot(version_id, data, data_type)
        version_record['snapshot_path'] = snapshot_path
        
        # 添加到版本列表
        self.versions.insert(0, version_record)
        
        # 只保留最近100个版本记录
        if len(self.versions) > 100:
            # 删除旧版本的快照文件
            for old_version in self.versions[100:]:
                self._delete_snapshot(old_version.get('snapshot_path'))
            self.versions = self.versions[:100]
        
        # 保存版本记录
        self._save_versions()
        
        logger.info(f"✅ 创建版本 {version_id}，数据类型: {data_type}，记录数: {len(data)}")
        return version_id
    
    def _save_snapshot(self, version_id: str, data: pd.DataFrame, data_type: str) -> str:
        """保存快照文件"""
        # 创建数据类型子目录
        type_dir = os.path.join(self.snapshot_dir, data_type)
        os.makedirs(type_dir, exist_ok=True)
        
        # 生成文件名
        filename = f"{version_id}.parquet"
        snapshot_path = os.path.join(type_dir, filename)
        
        # 保存为Parquet格式（高效压缩）
        try:
            data.to_parquet(snapshot_path, index=False)
            return snapshot_path
        except Exception as e:
            # 降级保存为CSV
            csv_path = snapshot_path.replace('.parquet', '.csv')
            data.to_csv(csv_path, index=False, encoding='utf-8')
            logger.warning(f"Parquet保存失败，降级为CSV: {str(e)}")
            return csv_path
    
    def _delete_snapshot(self, snapshot_path: Optional[str]):
        """删除快照文件"""
        if snapshot_path and os.path.exists(snapshot_path):
            try:
                os.remove(snapshot_path)
                logger.debug(f"删除快照: {snapshot_path}")
            except Exception as e:
                logger.warning(f"删除快照失败: {str(e)}")
    
    def load_version(self, version_id: str) -> Optional[pd.DataFrame]:
        """
        加载指定版本的数据
        
        Args:
            version_id: 版本ID
        
        Returns:
            数据DataFrame，如果不存在返回None
        """
        # 查找版本记录
        version_record = next((v for v in self.versions if v['version_id'] == version_id), None)
        
        if not version_record:
            logger.warning(f"版本 {version_id} 不存在")
            return None
        
        snapshot_path = version_record.get('snapshot_path')
        if not snapshot_path or not os.path.exists(snapshot_path):
            logger.warning(f"快照文件不存在: {snapshot_path}")
            return None
        
        # 加载数据
        try:
            if snapshot_path.endswith('.parquet'):
                return pd.read_parquet(snapshot_path)
            else:
                return pd.read_csv(snapshot_path, encoding='utf-8')
        except Exception as e:
            logger.error(f"加载版本失败: {str(e)}")
            return None
    
    def rollback_to_version(self, version_id: str) -> bool:
        """
        回滚到指定版本
        
        Args:
            version_id: 目标版本ID
        
        Returns:
            是否成功
        """
        # 加载目标版本数据
        data = self.load_version(version_id)
        if data is None:
            return False
        
        # 获取数据类型
        version_record = next((v for v in self.versions if v['version_id'] == version_id), None)
        if not version_record:
            return False
        
        data_type = version_record['data_type']
        
        # 创建回滚版本（作为新版本记录）
        self.create_version(
            data_type=data_type,
            data=data,
            description=f"回滚到版本 {version_id}",
            tags=['rollback']
        )
        
        logger.info(f"✅ 回滚到版本 {version_id}")
        return True
    
    def get_version_list(self, data_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取版本列表
        
        Args:
            data_type: 可选，按数据类型过滤
        
        Returns:
            版本列表
        """
        if data_type:
            return [v for v in self.versions if v['data_type'] == data_type]
        return self.versions
    
    def get_version_info(self, version_id: str) -> Optional[Dict[str, Any]]:
        """
        获取版本详细信息
        
        Args:
            version_id: 版本ID
        
        Returns:
            版本信息，如果不存在返回None
        """
        return next((v for v in self.versions if v['version_id'] == version_id), None)
    
    def delete_version(self, version_id: str) -> bool:
        """
        删除指定版本
        
        Args:
            version_id: 版本ID
        
        Returns:
            是否成功
        """
        # 查找版本记录
        version_record = next((v for v in self.versions if v['version_id'] == version_id), None)
        
        if not version_record:
            logger.warning(f"版本 {version_id} 不存在")
            return False
        
        # 删除快照文件
        self._delete_snapshot(version_record.get('snapshot_path'))
        
        # 从版本列表中移除
        self.versions = [v for v in self.versions if v['version_id'] != version_id]
        
        # 保存版本记录
        self._save_versions()
        
        logger.info(f"✅ 删除版本 {version_id}")
        return True
    
    def create_periodic_snapshot(self, data_type: str, data: pd.DataFrame, period: str = 'daily') -> str:
        """
        创建定期快照
        
        Args:
            data_type: 数据类型
            data: 数据内容
            period: 周期（daily/weekly/monthly）
        
        Returns:
            版本ID
        """
        description = f"{period} snapshot"
        tags = [period, 'snapshot']
        return self.create_version(data_type, data, description, tags)
    
    def get_latest_version(self, data_type: str) -> Optional[Dict[str, Any]]:
        """
        获取指定数据类型的最新版本
        
        Args:
            data_type: 数据类型
        
        Returns:
            最新版本信息，如果不存在返回None
        """
        versions = self.get_version_list(data_type)
        if versions:
            return versions[0]
        return None
    
    def validate_version(self, version_id: str) -> bool:
        """
        验证版本数据完整性（比对哈希值）
        
        Args:
            version_id: 版本ID
        
        Returns:
            数据是否完整
        """
        version_record = self.get_version_info(version_id)
        if not version_record:
            return False
        
        data = self.load_version(version_id)
        if data is None:
            return False
        
        # 重新计算哈希并比对
        expected_hash = version_record['hash']
        actual_hash = self._calculate_hash(data)
        
        if expected_hash == actual_hash:
            logger.debug(f"版本 {version_id} 校验通过")
            return True
        else:
            logger.warning(f"版本 {version_id} 校验失败：哈希不匹配")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取版本管理统计信息"""
        stats = {
            'total_versions': len(self.versions),
            'data_types': list(set(v['data_type'] for v in self.versions)),
            'version_count_by_type': {},
            'storage_path': self.storage_path,
            'last_created_at': self.versions[0]['created_at'] if self.versions else None
        }
        
        # 按类型统计
        for v in self.versions:
            data_type = v['data_type']
            stats['version_count_by_type'][data_type] = stats['version_count_by_type'].get(data_type, 0) + 1
        
        return stats
    
    def export_versions(self, output_path: str) -> bool:
        """
        导出版本记录到文件
        
        Args:
            output_path: 输出文件路径
        
        Returns:
            是否成功
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.versions, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 版本记录导出到 {output_path}")
            return True
        except Exception as e:
            logger.error(f"导出版本记录失败: {str(e)}")
            return False
    
    def import_versions(self, input_path: str) -> bool:
        """
        导入版本记录
        
        Args:
            input_path: 输入文件路径
        
        Returns:
            是否成功
        """
        try:
            with open(input_path, 'r', encoding='utf-8') as f:
                imported_versions = json.load(f)
            
            # 合并版本记录（去重）
            existing_ids = set(v['version_id'] for v in self.versions)
            new_versions = [v for v in imported_versions if v['version_id'] not in existing_ids]
            
            self.versions = new_versions + self.versions
            
            # 保存
            self._save_versions()
            
            logger.info(f"✅ 导入 {len(new_versions)} 个版本记录")
            return True
        except Exception as e:
            logger.error(f"导入版本记录失败: {str(e)}")
            return False


# 数据血缘追踪类
class DataLineageTracker:
    """
    数据血缘追踪器 - 追踪数据的来源和处理过程
    
    功能：
    - 记录数据来源
    - 追踪数据处理流程
    - 支持数据血缘查询
    """
    
    def __init__(self):
        self.lineage_records = []
    
    def record_lineage(
        self,
        output_name: str,
        input_sources: List[str],
        process_type: str,
        process_params: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None
    ):
        """
        记录数据血缘关系
        
        Args:
            output_name: 输出数据名称
            input_sources: 输入数据源列表
            process_type: 处理类型（如 'clean', 'transform', 'feature', 'merge'）
            process_params: 处理参数
            timestamp: 时间戳（默认当前时间）
        """
        record = {
            'output_name': output_name,
            'input_sources': input_sources,
            'process_type': process_type,
            'process_params': process_params or {},
            'timestamp': timestamp or datetime.now().isoformat(),
            'lineage_id': self._generate_lineage_id()
        }
        
        self.lineage_records.append(record)
        
        # 只保留最近1000条记录
        if len(self.lineage_records) > 1000:
            self.lineage_records = self.lineage_records[-1000:]
        
        logger.debug(f"记录血缘: {output_name} <- {input_sources} [{process_type}]")
    
    def _generate_lineage_id(self) -> str:
        """生成血缘记录ID"""
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f"lin_{timestamp}"
    
    def get_lineage(self, output_name: str) -> List[Dict[str, Any]]:
        """
        获取指定输出数据的血缘关系
        
        Args:
            output_name: 输出数据名称
        
        Returns:
            血缘记录列表
        """
        return [r for r in self.lineage_records if r['output_name'] == output_name]
    
    def get_source_usage(self, source_name: str) -> List[Dict[str, Any]]:
        """
        获取指定数据源被使用的记录
        
        Args:
            source_name: 数据源名称
        
        Returns:
            使用记录列表
        """
        return [r for r in self.lineage_records if source_name in r['input_sources']]
    
    def get_lineage_graph(self) -> Dict[str, Any]:
        """
        获取血缘关系图（用于可视化）
        
        Returns:
            血缘图结构
        """
        graph = {
            'nodes': set(),
            'edges': []
        }
        
        for record in self.lineage_records:
            graph['nodes'].add(record['output_name'])
            for source in record['input_sources']:
                graph['nodes'].add(source)
                graph['edges'].append({
                    'source': source,
                    'target': record['output_name'],
                    'process': record['process_type']
                })
        
        graph['nodes'] = list(graph['nodes'])
        return graph
    
    def get_stats(self) -> Dict[str, Any]:
        """获取血缘追踪统计"""
        stats = {
            'total_records': len(self.lineage_records),
            'process_types': list(set(r['process_type'] for r in self.lineage_records)),
            'output_count': len(set(r['output_name'] for r in self.lineage_records)),
            'source_count': len(set(s for r in self.lineage_records for s in r['input_sources']))
        }
        return stats


# 全局版本管理器实例
_global_version_manager = None
_global_lineage_tracker = None


def get_version_manager() -> DataVersionManager:
    """获取全局版本管理器实例"""
    global _global_version_manager
    if _global_version_manager is None:
        _global_version_manager = DataVersionManager()
    return _global_version_manager


def get_lineage_tracker() -> DataLineageTracker:
    """获取全局血缘追踪器实例"""
    global _global_lineage_tracker
    if _global_lineage_tracker is None:
        _global_lineage_tracker = DataLineageTracker()
    return _global_lineage_tracker


# 测试代码
if __name__ == '__main__':
    # 创建版本管理器
    vm = DataVersionManager()
    
    # 创建测试数据
    test_data = pd.DataFrame({
        'code': ['sh.600000', 'sh.600001', 'sh.600002'],
        'name': ['浦发银行', '邯郸钢铁', '齐鲁石化'],
        'close': [10.5, 5.3, 8.7]
    })
    
    # 创建版本
    version_id = vm.create_version('test', test_data, '测试数据版本', ['test', 'initial'])
    print(f"创建版本: {version_id}")
    
    # 获取版本信息
    info = vm.get_version_info(version_id)
    print(f"\n版本信息: {info}")
    
    # 加载版本
    loaded_data = vm.load_version(version_id)
    print(f"\n加载的数据:\n{loaded_data}")
    
    # 获取版本列表
    versions = vm.get_version_list()
    print(f"\n版本列表数量: {len(versions)}")
    
    # 获取统计信息
    stats = vm.get_stats()
    print(f"\n统计信息: {stats}")
    
    # 测试血缘追踪
    tracker = DataLineageTracker()
    tracker.record_lineage('processed_data', ['raw_data', 'reference_data'], 'transform', {'method': 'normalize'})
    tracker.record_lineage('final_result', ['processed_data', 'features'], 'merge')
    
    lineage = tracker.get_lineage('final_result')
    print(f"\n血缘关系: {lineage}")
    
    graph = tracker.get_lineage_graph()
    print(f"\n血缘图节点: {graph['nodes']}")
    print(f"血缘图边: {graph['edges']}")