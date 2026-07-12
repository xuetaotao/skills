// utils/banks.js —— 预置主流银行(录入时直接选,少打字)
const BANKS = [
  '工商银行', '农业银行', '中国银行', '建设银行', '交通银行', '邮储银行',
  '招商银行', '中信银行', '光大银行', '民生银行', '平安银行', '兴业银行',
  '浦发银行', '华夏银行', '广发银行', '浙商银行', '渤海银行', '恒丰银行',
  '北京银行', '上海银行', '江苏银行', '宁波银行', '南京银行', '杭州银行',
  '其他'
]

// 卡片类型
const CARD_TYPES = ['普卡', '金卡', '白金卡', '钻石卡', '商务卡', '其他']

// 减免类型
const WAIVER_TYPES = [
  { value: 'count', label: '笔数达标' },
  { value: 'amount', label: '金额达标' },
  { value: 'none', label: '无条件/必缴' },
  { value: 'manual', label: '手动标记' }
]

module.exports = { BANKS, CARD_TYPES, WAIVER_TYPES }
