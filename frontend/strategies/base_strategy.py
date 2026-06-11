"""
base_strategy.py - 策略抽象基类

【设计目标】
所有策略必须继承 BaseStrategy，并实现 generate_signals() 方法。
信号类型：
  - 'buy'  买入
  - 'sell' 卖出
  - 'hold' 持有（无操作）

【反前视偏差硬约束】
- generate_signals() 只能基于当前及历史数据
- 严禁使用 shift(-N) 引用未来数据
- 严禁使用 bfill（后向填充）
- 严禁在 on_bar() 中调用 get_future_data()
"""

from abc import ABC, abstractmethod
from typing import Dict, List
import pandas as pd

from shared.constants import SignalType


class BaseStrategy(ABC):
    """
    策略基类

    使用示例：
    ```python
    class MyStrategy(BaseStrategy):
        name = 'my_strategy'
        params = {'fast': 5, 'slow': 20}

        def generate_signals(self, df):
            signals = []
            for i in range(len(df)):
                if i < self.params['slow']:
                    signals.append('hold')
                    continue
                fast_ma = df['close'].iloc[i-5:i].mean()
                slow_ma = df['close'].iloc[i-20:i].mean()
                if fast_ma > slow_ma:
                    signals.append('buy')
                else:
                    signals.append('sell')
            return signals
    ```
    """

    # 策略元数据（子类必须重写）
    name: str = 'base_strategy'
    description: str = 'Base strategy, do not use directly'
    params: Dict = {}

    def __init__(self, **kwargs):
        """允许通过 kwargs 覆盖默认参数"""
        self.params = {**self.params, **kwargs}

    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> List[str]:
        """
        生成所有 K 线对应的信号

        Args:
            df: K线 DataFrame, columns = [trade_date, open, high, low, close, volume, ...]
                索引必须按时间升序

        Returns:
            List[str], 长度 == len(df), 元素 ∈ {'buy', 'sell', 'hold'}

        【硬约束】只能使用 df.iloc[:i+1] 的数据，不能引用未来
        """
        raise NotImplementedError

    def on_bar(self, bar: Dict) -> str:
        """
        事件驱动接口（实盘模拟）

        Args:
            bar: 当前 K 线数据 {'trade_date', 'open', 'high', 'low', 'close', 'volume'}

        Returns:
            'buy' / 'sell' / 'hold'
        """
        # 默认实现：把单根 bar 累积到内部 df，调用 generate_signals 取最后一个
        if not hasattr(self, '_df_buffer'):
            self._df_buffer = []
        self._df_buffer.append(bar)
        df = pd.DataFrame(self._df_buffer)
        signals = self.generate_signals(df)
        return signals[-1] if signals else 'hold'

    def get_params(self) -> Dict:
        return self.params.copy()

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.params}>'
