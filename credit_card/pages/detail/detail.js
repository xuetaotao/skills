// pages/detail/detail.js(纯本地存储版)
const { getById, remove } = require('../../utils/storage')
const { getCycleInfo, getWaiverStatus, getProgressPercent, waiverTypeLabel }
  = require('../../utils/annualFee')

Page({
  data: {
    id: '',
    card: null,
    cycle: null,
    status: '',
    statusText: '',
    percent: 0,
    diff: 0,
    waiverLabel: ''
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ id: options.id })
    }
  },

  onShow() {
    if (this.data.id) this.loadCard(this.data.id)
  },

  loadCard(id) {
    const c = getById(id)
    if (!c) {
      wx.showToast({ title: '未找到该卡片', icon: 'none' })
      return
    }
    const cycle = getCycleInfo(c.activationDate)
    const status = getWaiverStatus(c)
    const percent = getProgressPercent(c)
    const statusText = status === 'met' ? '已达标'
      : status === 'unmet' ? '未达标' : '待确认'
    this.setData({
      card: c,
      cycle,
      status,
      statusText,
      percent,
      diff: (Number(c.waiverTarget) || 0) - (Number(c.waiverProgress) || 0),
      waiverLabel: waiverTypeLabel(c.waiverType)
    })
  },

  goEdit() {
    wx.navigateTo({ url: `/pages/add/add?id=${this.data.id}` })
  },

  remove() {
    wx.showModal({
      title: '删除卡片',
      content: '确定删除这张卡片吗?此操作不可恢复(数据仅存本机)。',
      confirmColor: '#fa5151',
      success: (r) => {
        if (!r.confirm) return
        remove(this.data.id)
        wx.showToast({ title: '已删除', icon: 'success' })
        setTimeout(() => wx.navigateBack(), 600)
      }
    })
  }
})
