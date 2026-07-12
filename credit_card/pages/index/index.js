// pages/index/index.js —— 卡片列表 + 仪表盘(纯本地存储版)
const { getAll } = require('../../utils/storage')
const { getCycleInfo, getProgressPercent, getWaiverStatus }
  = require('../../utils/annualFee')

Page({
  data: {
    cards: [],
    stats: { total: 0, met: 0, unmet: 0, unknown: 0 },
    alerts: [] // 临近截止且未达标
  },

  onShow() {
    this.loadCards()
  },

  onPullDownRefresh() {
    this.loadCards(() => wx.stopPullDownRefresh())
  },

  loadCards(cb) {
    let raw = getAll()
    raw.sort((a, b) => new Date(b.updatedAt || 0) - new Date(a.updatedAt || 0))
    const cards = raw.map(c => {
      const cycle = getCycleInfo(c.activationDate)
      const status = getWaiverStatus(c)
      const percent = getProgressPercent(c)
      return Object.assign({}, c, { cycle, status, percent })
    })
    const met = cards.filter(c => c.status === 'met').length
    const unmet = cards.filter(c => c.status === 'unmet').length
    const unknown = cards.filter(c => c.status === 'unknown').length
    const alerts = cards
      .filter(c => c.status === 'unmet' && c.cycle && c.cycle.daysLeft <= 30)
      .sort((a, b) => a.cycle.daysLeft - b.cycle.daysLeft)
    this.setData({
      cards,
      stats: { total: cards.length, met, unmet, unknown },
      alerts
    })
    cb && cb()
  },

  goAdd() {
    wx.navigateTo({ url: '/pages/add/add' })
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    wx.navigateTo({ url: `/pages/detail/detail?id=${id}` })
  }
})
