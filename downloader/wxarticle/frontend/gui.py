# -*- coding: utf-8 -*-
"""
公众号文章下载 - PyQt5 图形界面
下载在后台 QThread 里跑自己的 asyncio 事件循环，复用 backend.core.download_articles 的完整流程。
"""

import asyncio
import os
import sys

from PyQt5.QtCore import QSettings, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QColor, QDesktopServices, QKeySequence
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog,
                             QFileDialog, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QShortcut, QTableWidget, QTableWidgetItem, QVBoxLayout)

from backend.config import OUTPUT_DIR, SCALE
from backend.core import Reporter, download_articles, extract_urls
from backend.fetcher import ArticleError

COLUMNS = ('状态', '标题', '公众号', '发布时间', '说明')
STATUS_COLORS = {'完成': '#2E7D32', '失败': '#C62828', '已取消': '#9E9E9E'}


class _SignalReporter(Reporter):
    """在下载线程里被调用，转成信号交给界面线程（不把 Playwright 对象传出线程）。"""

    def __init__(self, worker):
        self.worker = worker

    def start(self, index, total, url):
        self.worker.article_started.emit(index)

    def article(self, index, article):
        self.worker.article_loaded.emit(index, {
            'title': article.title, 'account': article.account,
            'publish_time': article.publish_time, 'images': article.images,
            'failed_images': article.failed_images})

    def finished(self, index, result):
        self.worker.article_finished.emit(index, result)


class Worker(QThread):
    article_started = pyqtSignal(int)
    article_loaded = pyqtSignal(int, object)    # 序号, 标题等信息
    article_finished = pyqtSignal(int, object)  # 序号, backend.core.Result
    done = pyqtSignal(bool, str)                # 是否取消, 致命错误（如没装 Chromium）

    def __init__(self, urls, **options):
        super().__init__()
        self.urls = urls
        self.options = options
        self._loop = None
        self._task = None
        self._cancelled = False

    def run(self):
        try:
            asyncio.run(self._main())
            self.done.emit(self._cancelled, '')
        except asyncio.CancelledError:
            self.done.emit(True, '')
        except ArticleError as e:
            self.done.emit(False, str(e))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.done.emit(False, f'{type(e).__name__}: {e}')

    async def _main(self):
        self._task = asyncio.current_task()
        self._loop = asyncio.get_running_loop()
        # 取消时浏览器被关掉，Playwright 里还没完成的请求会报“Future exception was never retrieved”
        self._loop.set_exception_handler(
            lambda loop, ctx: None if self._cancelled else loop.default_exception_handler(ctx))
        if self._cancelled:
            return
        await download_articles(self.urls, reporter=_SignalReporter(self), **self.options)

    def cancel(self):
        """可在界面线程调用：取消正在进行的那篇，浏览器随之关闭。"""
        self._cancelled = True
        if self._loop and self._task:
            self._loop.call_soon_threadsafe(self._task.cancel)


class ArticleDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("公众号文章下载")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.resize(860, 620)
        self.settings = QSettings('skills-downloader', 'wxarticle')
        self.worker = None
        self.results = {}
        self._build_ui()
        self._load_settings()

    # ---------- 界面 ----------
    def _build_ui(self):
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("文章链接:"))
        row.addStretch(1)
        self.count_label = QLabel()
        self.count_label.setStyleSheet("color:#666")
        row.addWidget(self.count_label)
        layout.addLayout(row)

        self.url_edit = QPlainTextEdit()
        self.url_edit.setPlaceholderText(
            "粘贴一个或多个公众号文章链接，每行一个；\n"
            "也可以直接粘贴“标题 + 链接”混在一起的文字，会自动识别、去重。\n"
            "Ctrl+Enter 开始下载")
        self.url_edit.setMaximumHeight(110)
        self.url_edit.textChanged.connect(self._update_count)
        layout.addWidget(self.url_edit)

        row = QHBoxLayout()
        row.addWidget(QLabel("输出目录:"))
        self.output_edit = QLineEdit()
        row.addWidget(self.output_edit)
        btn = QPushButton("浏览")
        btn.clicked.connect(self._browse)
        row.addWidget(btn)
        layout.addLayout(row)

        opts = QGroupBox("选项")
        row = QHBoxLayout(opts)
        self.check_pdf = QCheckBox("PDF")
        self.check_shot = QCheckBox("长截图")
        self.check_pdf.setToolTip("A4 排版，可打印、可搜索文字")
        self.check_shot.setToolTip("只截正文栏，超长文章会自动拆成多张")
        self.combo_scale = QComboBox()
        self.combo_scale.addItem("高清（2 倍）", 2)
        self.combo_scale.addItem("标准（1 倍，文件约小 2/3）", 1)
        self.check_shot.toggled.connect(self.combo_scale.setEnabled)
        self.check_show = QCheckBox("显示浏览器窗口")
        self.check_show.setToolTip("遇到微信“环境异常”验证时勾选，可以在弹出的浏览器里手动完成验证")
        row.addWidget(self.check_pdf)
        row.addWidget(self.check_shot)
        row.addWidget(QLabel("截图清晰度:"))
        row.addWidget(self.combo_scale)
        row.addSpacing(16)
        row.addWidget(self.check_show)
        row.addStretch(1)
        layout.addWidget(opts)

        row = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setDefault(True)
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_open = QPushButton("打开保存位置")
        self.btn_open.clicked.connect(self._open_output)
        for b in (self.btn_start, self.btn_cancel, self.btn_open):
            row.addWidget(b)
        layout.addLayout(row)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._on_start)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._on_start)

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFormat("")
        self.progress.setValue(0)
        self.status = QLabel("就绪")
        row.addWidget(self.progress, 1)
        row.addWidget(self.status)
        layout.addLayout(row)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        for col, mode in enumerate((QHeaderView.ResizeToContents, QHeaderView.Stretch,
                                    QHeaderView.ResizeToContents, QHeaderView.ResizeToContents,
                                    QHeaderView.Interactive)):
            header.setSectionResizeMode(col, mode)
        header.resizeSection(4, 230)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.cellDoubleClicked.connect(lambda r, _c: self._open_result(r))
        layout.addWidget(self.table, 1)

        tip = QLabel("双击一行打开生成的文件，右键可以打开 PDF / 截图 / 所在文件夹或原文")
        tip.setStyleSheet("color:#888")
        layout.addWidget(tip)
        self._update_count()

    # ---------- 设置 ----------
    def _load_settings(self):
        s = self.settings
        self.output_edit.setText(s.value('output', str(OUTPUT_DIR)))
        self.check_pdf.setChecked(s.value('pdf', 'true') == 'true')
        self.check_shot.setChecked(s.value('screenshot', 'true') == 'true')
        index = self.combo_scale.findData(int(s.value('scale', SCALE)))
        self.combo_scale.setCurrentIndex(max(index, 0))
        self.combo_scale.setEnabled(self.check_shot.isChecked())
        self.check_show.setChecked(s.value('show_browser', 'false') == 'true')

    def _save_settings(self):
        s = self.settings
        s.setValue('output', self.output_edit.text().strip())
        s.setValue('pdf', 'true' if self.check_pdf.isChecked() else 'false')
        s.setValue('screenshot', 'true' if self.check_shot.isChecked() else 'false')
        s.setValue('scale', self.combo_scale.currentData())
        s.setValue('show_browser', 'true' if self.check_show.isChecked() else 'false')

    # ---------- 交互 ----------
    def _urls(self):
        return extract_urls([self.url_edit.toPlainText()])

    def _update_count(self):
        n = len(self._urls())
        self.count_label.setText(f"识别到 {n} 个链接" if n else "")

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _open_path(self, path):
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _open_output(self):
        path = self.output_edit.text().strip()
        if path and not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        self._open_path(path)

    def _on_start(self):
        if self.worker and self.worker.isRunning():
            return
        urls = self._urls()
        if not urls:
            QMessageBox.warning(self, "提示", "没有识别到文章链接（以 http:// 或 https:// 开头）")
            return
        if not (self.check_pdf.isChecked() or self.check_shot.isChecked()):
            QMessageBox.warning(self, "提示", "PDF 和长截图至少勾选一个")
            return
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return
        self._save_settings()

        self.results = {}
        self.table.setRowCount(0)
        for url in urls:
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, text in enumerate(('等待', url, '', '', '')):
                self.table.setItem(row, col, QTableWidgetItem(text))

        self.worker = Worker(
            urls, output_dir=output, pdf=self.check_pdf.isChecked(),
            screenshot=self.check_shot.isChecked(), headless=not self.check_show.isChecked(),
            scale=self.combo_scale.currentData())
        self.worker.article_started.connect(self._on_article_started)
        self.worker.article_loaded.connect(self._on_article_loaded)
        self.worker.article_finished.connect(self._on_article_finished)
        self.worker.done.connect(self._on_done)
        self.progress.setFormat("%v / %m")
        self.progress.setRange(0, len(urls))
        self.progress.setValue(0)
        self.status.setText("正在启动浏览器…")
        self._set_running(True)
        self.worker.start()

    def _set_running(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        for w in (self.url_edit, self.output_edit, self.check_pdf, self.check_shot,
                  self.combo_scale, self.check_show):
            w.setEnabled(not running)
        if not running:
            self.combo_scale.setEnabled(self.check_shot.isChecked())

    def _set_cell(self, row, col, text, tooltip=None, color=None):
        item = self.table.item(row, col)
        item.setText(text)
        item.setToolTip(tooltip if tooltip is not None else text)
        if color:
            item.setForeground(QColor(color))

    def _on_article_started(self, row):
        self._set_cell(row, 0, '打开中…')
        self.table.scrollToItem(self.table.item(row, 0))
        self.status.setText(f"正在处理第 {row + 1} 篇…")

    def _on_article_loaded(self, row, info):
        self._set_cell(row, 0, '保存中…')
        self._set_cell(row, 1, info['title'], tooltip=self.table.item(row, 1).text())
        self._set_cell(row, 2, info['account'])
        self._set_cell(row, 3, info['publish_time'])
        self._set_cell(row, 4, self._image_note(info['images'], info['failed_images']))

    @staticmethod
    def _image_note(images, failed):
        return f"图片 {images} 张" + (f"，{failed} 张没加载出来" if failed else '')

    def _on_article_finished(self, row, result):
        self.results[row] = result
        self.progress.setValue(len(self.results))
        if result.ok:
            files = ([result.pdf] if result.pdf else []) + result.screenshots
            note = f"{self._image_note(result.images, result.failed_images)} · {result.seconds:.1f} 秒"
            self._set_cell(row, 0, '完成', color=STATUS_COLORS['完成'])
            self._set_cell(row, 4, note, tooltip='\n'.join(str(p) for p in files))
        else:
            self._set_cell(row, 0, '失败', color=STATUS_COLORS['失败'])
            self._set_cell(row, 4, result.error)

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("正在取消…")
            self.btn_cancel.setEnabled(False)

    def _on_done(self, cancelled, error):
        self._set_running(False)
        for row in range(self.table.rowCount()):
            if row not in self.results:
                self._set_cell(row, 0, '已取消' if cancelled or error else '未处理',
                               color=STATUS_COLORS['已取消'])
        ok = sum(r.ok for r in self.results.values())
        failed = len(self.results) - ok
        if error:
            self.status.setText("启动失败")
            QMessageBox.critical(self, "出错了", error)
        elif cancelled:
            self.status.setText(f"已取消：完成 {ok} 篇" + (f"，失败 {failed} 篇" if failed else ''))
        else:
            self.status.setText(f"完成：成功 {ok} 篇" + (f"，失败 {failed} 篇" if failed else ''))

    # ---------- 结果表格 ----------
    def _open_result(self, row):
        result = self.results.get(row)
        if result and result.ok:
            self._open_path(result.pdf or (result.screenshots[0] if result.screenshots else None))

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0:
            return
        result = self.results.get(row)
        url = self.table.item(row, 1).toolTip() or self.table.item(row, 1).text()
        menu = QMenu(self)
        if result and result.ok:
            if result.pdf:
                menu.addAction("打开 PDF", lambda: self._open_path(result.pdf))
            for i, shot in enumerate(result.screenshots):
                label = "打开截图" if len(result.screenshots) == 1 else f"打开截图 {i + 1}"
                menu.addAction(label, lambda p=shot: self._open_path(p))
            first = result.pdf or result.screenshots[0]
            menu.addAction("打开所在文件夹", lambda: self._open_path(os.path.dirname(first)))
            menu.addSeparator()
        menu.addAction("在浏览器中打开原文", lambda: QDesktopServices.openUrl(QUrl(url)))
        menu.addAction("复制链接", lambda: QApplication.clipboard().setText(url))
        menu.exec_(self.table.viewport().mapToGlobal(pos))

    def closeEvent(self, event):
        self._save_settings()
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(15000)
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    dlg = ArticleDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
