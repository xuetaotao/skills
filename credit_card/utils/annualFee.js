// utils/annualFee.js
// 年费周期计算 + 达标判定工具(小程序端和云函数端通用)

// 日期格式化为 YYYY-MM-DD
function formatDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// 根据启卡日期和当前日期,返回当前年费周期信息
// activationDate: 'YYYY-MM-DD'
// now: Date 对象(默认当前)
function getCycleInfo(activationDate, now) {
  if (!activationDate) return null
  const act = new Date(activationDate.replace(/-/g, '/'))
  if (isNaN(act.getTime())) return null

  now = now || new Date()
  const actMonth = act.getMonth()
  const actDay = act.getDate()

  const curYear = now.getFullYear()
  const curMonth = now.getMonth()
  const curDay = now.getDate()

  // 判断当前处于哪个周期:还没到今年的启卡日 -> 周期从去年启卡日开始
  let startYear
  if (curMonth < actMonth || (curMonth === actMonth && curDay < actDay)) {
    startYear = curYear - 1
  } else {
    startYear = curYear
  }

  const cycleStart = new Date(startYear, actMonth, actDay)
  // 周期结束 = 下一个启卡日 - 1 天
  const cycleEnd = new Date(startYear + 1, actMonth, actDay)
  cycleEnd.setDate(cycleEnd.getDate() - 1)

  // 距周期结束天数(过期记为 0)
  const diffMs = cycleEnd - now
  const daysLeft = diffMs > 0 ? Math.ceil(diffMs / (1000 * 60 * 60 * 24)) : 0

  return {
    cycleStart: formatDate(cycleStart),
    cycleEnd: formatDate(cycleEnd),
    daysLeft: daysLeft
  }
}

// 达标状态: 'met' 已达标 | 'unmet' 未达标 | 'unknown' 无法自动判定
// 减免类型 waiverType: 'count'(笔数) | 'amount'(金额) | 'none'(无条件/必缴) | 'manual'(手动)
function getWaiverStatus(card) {
  const { waiverType, waiverTarget, waiverProgress } = card
  if (!waiverType || waiverType === 'none' || waiverType === 'manual') {
    return 'unknown'
  }
  const target = Number(waiverTarget) || 0
  const progress = Number(waiverProgress) || 0
  if (target <= 0) return 'unknown'
  return progress >= target ? 'met' : 'unmet'
}

// 达标进度百分比 0~100
function getProgressPercent(card) {
  const { waiverType, waiverTarget, waiverProgress } = card
  if (!waiverType || waiverType === 'none' || waiverType === 'manual') return 0
  const target = Number(waiverTarget) || 0
  const progress = Number(waiverProgress) || 0
  if (target <= 0) return 0
  return Math.min(100, Math.round((progress / target) * 100))
}

// 减免类型的中文 + 单位
function waiverTypeLabel(waiverType) {
  switch (waiverType) {
    case 'count': return '笔数'
    case 'amount': return '金额'
    case 'none': return '无条件/必缴'
    case 'manual': return '手动'
    default: return ''
  }
}

module.exports = {
  formatDate,
  getCycleInfo,
  getWaiverStatus,
  getProgressPercent,
  waiverTypeLabel
}
