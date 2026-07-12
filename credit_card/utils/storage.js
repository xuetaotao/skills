// utils/storage.js —— 本地存储(替代云数据库)
// 数据保存在本机 wx.storage,无需任何云服务。单 key 存一个数组。
const KEY = 'cards'

function getAll() {
  return wx.getStorageSync(KEY) || []
}

function getById(id) {
  return getAll().find(c => c.id === id) || null
}

function save(card) {
  const list = getAll()
  if (card.id) {
    const idx = list.findIndex(c => c.id === card.id)
    if (idx >= 0) {
      list[idx] = Object.assign({}, list[idx], card, { updatedAt: Date.now() })
    } else {
      card.createdAt = Date.now()
      card.updatedAt = Date.now()
      list.push(card)
    }
  } else {
    card.id = genId()
    card.createdAt = Date.now()
    card.updatedAt = Date.now()
    list.push(card)
  }
  wx.setStorageSync(KEY, list)
  return card
}

function remove(id) {
  const list = getAll().filter(c => c.id !== id)
  wx.setStorageSync(KEY, list)
}

function genId() {
  return 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8)
}

module.exports = { getAll, getById, save, remove }
