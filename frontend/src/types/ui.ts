// 通用 UI 组件的公共类型，页面与组件共用。

export interface SegmentOption<V = string | number> {
  label: string
  value: V
  color?: string
}

export interface StatItem {
  key?: string
  label: string
  value: string | number | null | undefined
  foot?: string
  /** 例如 price-up / price-down */
  cls?: string
  color?: string
}

export type ColumnType =
  | 'text'     // 原样文本
  | 'num'      // 千分位数字
  | 'price'    // 价格，按 by 字段（默认 changePercent）涨跌染色
  | 'change'   // 涨跌幅，带正负号并染色
  | 'percent'  // 普通百分比（ROE 等），不染色
  | 'score'    // 评分胶囊
  | 'signal'   // 看多/看空/中性标签
  | 'amount'   // 金额，按用户偏好的 亿/万 单位显示

export interface StockColumn {
  key: string
  label: string
  type?: ColumnType
  align?: 'left' | 'center' | 'right'
  width?: number | string
  digits?: number
  /** price / amount / num 类型按哪个字段的正负染色；amount ��认按自身 */
  by?: string
  /** amount / num 是否按正负染色 */
  colored?: boolean
  /** 数值后缀，如 "%" / "万股" */
  suffix?: string
  /** 表头提示 */
  tooltip?: string
  sortable?: boolean
  /** 自定义取值 / 文本 */
  format?: (row: any) => string | number | null | undefined
  /** 手机卡片里的位置：primary 右侧大字 / secondary 底部小字 / title 作为标题 / hidden 不显示 */
  mobile?: 'primary' | 'secondary' | 'title' | 'hidden'
}
