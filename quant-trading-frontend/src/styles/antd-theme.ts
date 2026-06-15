import { theme } from 'antd';

export const antdThemeConfig = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#26A69A', 
    colorBgBase: '#131722',
    colorBgContainer: '#1E222D',
    colorBgElevated: '#2A2E39',
    colorTextBase: '#EAECEF',
    colorBorder: '#2A2E39',
    colorBorderSecondary: '#3A3E49',
    borderRadius: 4,
  },
  components: {
    Menu: {
      itemBg: 'transparent',
      subMenuItemBg: '#1E222D',
    },
    Table: {
      headerBg: '#1E222D',
      rowHoverBg: '#2A2E39',
    },
  }
};