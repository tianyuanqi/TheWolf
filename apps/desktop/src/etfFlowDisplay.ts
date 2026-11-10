import type { EtfView } from './etfFlowClient';

/** 格式化服务端十进制结果，缺值与真实零区分；单位转换不产生业务结论。 */
export function etfNumber(value: string | null | undefined, divisor = 1, digits = 2): string {
  if (value === null || value === undefined) return '—';
  const number = Number(value) / divisor;
  if (number === 0) return '0';
  if (Math.abs(number) < 10 ** -digits) return `${number < 0 ? '−' : '+'}<${(10 ** -digits).toFixed(digits)}`;
  return number.toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
export const etfPercent = (value: string | null | undefined) => value == null ? '—' : etfNumber(value, .01) + '%';
export const etfAmount = (value: string | null | undefined) => value == null ? '—' : etfNumber(value, 1e8) + ' 亿元';
export const etfTone = (value: string | null | undefined) => value == null || Number(value) === 0 ? 'm-flat' : Number(value) > 0 ? 'm-up' : 'm-down';
export const etfTime = (value: string | null | undefined) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '未记录';
export const etfState = (state: EtfView['data_status']['state']) => ({ unrecorded: '当时未记录', insufficient: '数据不足',
  parameters_pending: '参数待确认', abnormal_subscription: '异常净申购线索', abnormal_redemption: '异常净赎回线索', not_triggered: '未触发' })[state];
