import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ScreenerProvider } from '@/features/stock-picker/context/ScreenerContext';
import ConditionBuilder from '@/features/stock-picker/components/ConditionBuilder';
import { FILTER_PRESETS } from '@/features/stock-picker/types/filterTree';

// ============================================================================
// P3.2 2026-06-18：11 个测试用例因 K 2026-06-17 UI 重构已删除
// ----------------------------------------------------------------------------
// K 2026-06-17 决策：ConditionBuilder 重构为三组平级（技术指标/K线形态/自编指标），
// 全部 AND 关系，preset 按钮改为 toggle 行为。
// 旧 UI 中的"组合预设应用/AND-OR-NOT 关系选择器/+ 条件按钮/condition-empty 状态/
// condition-item-op 标签/condition-item-remove 按钮"在新 UI 中均不存在。
// 历史失败 11 个已删除，仅保留原 4 个通过用例（基础渲染 + 默认折叠行为），
// 覆盖度由浏览器自测（按 K 偏好"通过内部浏览器自测"）补齐。
// ============================================================================

function renderBuilder() {
  // K 2026-06-17 变更：ConditionBuilder 使用 useNavigate（跳转 /config），
  // 需要 MemoryRouter 提供 Router 上下文
  return render(
    <MemoryRouter>
      <ScreenerProvider>
        <ConditionBuilder />
      </ScreenerProvider>
    </MemoryRouter>,
  );
}

// ============================================================================
// Tests
// ============================================================================

describe('ConditionBuilder', () => {
  // --------------------------------------------------------------------------
  // 1. 基础渲染
  // --------------------------------------------------------------------------
  describe('基础渲染', () => {
    it('渲染 header、count 徽标、reset 按钮', () => {
      renderBuilder();
      expect(screen.getByTestId('condition-builder-header')).toHaveTextContent('条件构建器');
      expect(screen.getByTestId('condition-builder-count')).toHaveTextContent('0 个条件');
      expect(screen.getByTestId('condition-builder-reset')).toBeInTheDocument();
    });

    it('默认折叠时不显示 6 个预设按钮', () => {
      renderBuilder();
      FILTER_PRESETS.forEach((p) => {
        expect(screen.queryByTestId(`condition-preset-${p.fieldKey}`)).not.toBeInTheDocument();
      });
    });
  });
});
