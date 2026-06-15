import React from 'react';
import { Typography, Button, Collapse } from 'antd';
import { SettingOutlined, RestOutlined } from '@ant-design/icons';
import { useScreener } from '../context/ScreenerContext';

const { Text } = Typography;
const { Panel } = Collapse;

const ConditionBuilder: React.FC = () => {
  const { state, dispatch } = useScreener();
  const { collapsedPanels } = state;

  const conditionCount = 0;

  const handleReset = () => {
    dispatch({ type: 'SET_CONDITION_TREE', payload: null });
  };

  const activeKey = collapsedPanels.condition ? ['condition'] : [];

  return (
    <Collapse
      activeKey={activeKey}
      ghost
      className="border-b border-border-color"
      onChange={() => dispatch({ type: 'TOGGLE_PANEL', payload: 'condition' })}
    >
      <Panel
        header={
          <span className="flex items-center justify-between w-full">
            <span className="flex items-center gap-2">
              <SettingOutlined className="text-color-up" />
              <Text className="text-text-primary font-semibold">条件构建器</Text>
            </span>
            <span className="flex items-center gap-2">
              <Text className="text-text-secondary text-sm">{conditionCount}个条件</Text>
              <Button
                type="text"
                size="small"
                icon={<RestOutlined />}
                onClick={handleReset}
                className="text-text-secondary hover:text-text-primary"
              >
                重置
              </Button>
            </span>
          </span>
        }
        key="condition"
      >
        <div className="text-text-secondary text-sm text-center py-4">暂无条件</div>
      </Panel>
    </Collapse>
  );
};

export default ConditionBuilder;
