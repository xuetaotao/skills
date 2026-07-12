// pages/add/add.js —— 新增 / 编辑卡片(纯本地存储版)
const { BANKS, CARD_TYPES, WAIVER_TYPES } = require('../../utils/banks')
const { getById, save } = require('../../utils/storage')

Page({
  data: {
    id: '',
    isEdit: false,
    banks: BANKS,
    cardTypes: CARD_TYPES,
    waiverTypes: WAIVER_TYPES,
    bankIndex: 0,
    cardTypeIndex: 0,
    waiverTypeIndex: -1,
    form: {
      cardLast4: '',
      creditLimit: '',
      activationDate: '',
      annualFee: '',
      waiverTarget: '',
      waiverProgress: '',
      billingDay: '',
      repaymentDay: '',
      remarks: ''
    }
  },

  onLoad(options) {
    if (options.id) {
      this.setData({ id: options.id, isEdit: true })
      wx.setNavigationBarTitle({ title: '编辑卡片' })
      this.loadCard(options.id)
    }
  },

  loadCard(id) {
    const c = getById(id)
    if (!c) {
      wx.showToast({ title: '未找到该卡片', icon: 'none' })
      return
    }
    const bankIndex = BANKS.indexOf(c.bank)
    const cardTypeIndex = CARD_TYPES.indexOf(c.cardType)
    const waiverTypeIndex = WAIVER_TYPES.findIndex(w => w.value === c.waiverType)
    this.setData({
      bankIndex: bankIndex >= 0 ? bankIndex : 0,
      cardTypeIndex: cardTypeIndex >= 0 ? cardTypeIndex : 0,
      waiverTypeIndex: waiverTypeIndex >= 0 ? waiverTypeIndex : 0,
      form: {
        cardLast4: c.cardLast4 || '',
        creditLimit: c.creditLimit || '',
        activationDate: c.activationDate || '',
        annualFee: c.annualFee || '',
        waiverTarget: c.waiverTarget || '',
        waiverProgress: c.waiverProgress || '',
        billingDay: c.billingDay || '',
        repaymentDay: c.repaymentDay || '',
        remarks: c.remarks || ''
      }
    })
  },

  onBankChange(e) { this.setData({ bankIndex: Number(e.detail.value) }) },
  onCardTypeChange(e) { this.setData({ cardTypeIndex: Number(e.detail.value) }) },
  onWaiverTypeChange(e) { this.setData({ waiverTypeIndex: Number(e.detail.value) }) },
  onDateChange(e) { this.setData({ 'form.activationDate': e.detail.value }) },
  onInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ [`form.${field}`]: e.detail.value })
  },

  save() {
    const { bankIndex, cardTypeIndex, waiverTypeIndex, form, isEdit, id } = this.data
    const bank = BANKS[bankIndex]
    const cardType = CARD_TYPES[cardTypeIndex]
    const waiverType = waiverTypeIndex >= 0 ? WAIVER_TYPES[waiverTypeIndex].value : ''

    if (!form.activationDate) {
      wx.showToast({ title: '请选择启卡日期', icon: 'none' })
      return
    }

    const data = {
      bank,
      cardType,
      cardLast4: form.cardLast4,
      creditLimit: Number(form.creditLimit) || 0,
      activationDate: form.activationDate,
      annualFee: Number(form.annualFee) || 0,
      waiverType,
      waiverTarget: Number(form.waiverTarget) || 0,
      waiverProgress: Number(form.waiverProgress) || 0,
      billingDay: Number(form.billingDay) || 0,
      repaymentDay: Number(form.repaymentDay) || 0,
      remarks: form.remarks
    }
    if (isEdit) data.id = id

    wx.showLoading({ title: '保存中' })
    try {
      save(data)
      wx.hideLoading()
      wx.showToast({ title: '已保存', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 600)
    } catch (err) {
      console.error(err)
      wx.hideLoading()
      wx.showToast({ title: '保存失败', icon: 'none' })
    }
  }
})
