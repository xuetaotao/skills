# -*- coding: utf-8 -*-
"""
网页图片下载器 - PyQt5 图形界面
下载在后台 QThread 中运行，复用 backend.core.WebpageImageDownloader 的完整流程。
"""

import os
import sys

from PyQt5.QtCore import QSettings, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QGridLayout,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout)

from backend.config import NUM_THREADS, OUTPUT_DIR, TIMEOUT
from backend.core import WebpageImageDownloader


class DownloaderWorker(QThread):
    log = pyqtSignal(str)
    count = pyqtSignal(int, int)
    done = pyqtSignal(bool, bool, str)  # 成功, 是否取消, 输出目录

    def __init__(self, **kwargs):
        super().__init__()
        self.downloader = WebpageImageDownloader(log=self.log.emit, progress=self.count.emit, **kwargs)

    def run(self):
        d = self.downloader
        try:
            ok = d.run()
        except Exception as e:
            import traceback
            self.log.emit(f"[!] 出现异常: {e}\n{traceback.format_exc()}")
            ok = False
        self.done.emit(ok, d.stop_event.is_set(), d.output_dir or '')

    def stop(self):
        self.downloader.cancel()


class WebpageDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("网页图片下载器")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.resize(760, 560)
        self.settings = QSettings('skills-downloader', 'image')
        self.worker = None
        self.last_output_dir = ''
        self._build_ui()
        self._load_settings()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("网页 URL:"))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("粘贴图集/文章页面地址，回车开始下载")
        self.url_edit.returnPressed.connect(self._on_start)
        row.addWidget(self.url_edit)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("输出目录:"))
        self.output_edit = QLineEdit()
        row.addWidget(self.output_edit)
        btn = QPushButton("浏览")
        btn.clicked.connect(self._browse)
        row.addWidget(btn)
        layout.addLayout(row)

        opts = QGroupBox("选项")
        grid = QGridLayout(opts)

        self.spin_threads = QSpinBox()
        self.spin_threads.setRange(1, 32)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(5, 300)
        grid.addWidget(QLabel("线程数:"), 0, 0)
        grid.addWidget(self.spin_threads, 0, 1)
        grid.addWidget(QLabel("超时(秒):"), 0, 2)
        grid.addWidget(self.spin_timeout, 0, 3)

        self.check_pagination = QCheckBox("自动翻页")
        self.check_pagination.setToolTip("自动识别分页并下载所有页面的图片")
        self.spin_max_pages = QSpinBox()
        self.spin_max_pages.setRange(0, 9999)
        self.spin_max_pages.setSpecialValueText("不限")
        self.check_pagination.toggled.connect(self.spin_max_pages.setEnabled)
        grid.addWidget(self.check_pagination, 1, 0)
        grid.addWidget(QLabel("最多页数:"), 1, 2)
        grid.addWidget(self.spin_max_pages, 1, 3)

        self.check_min_size = QCheckBox("跳过小图片")
        self.check_min_size.setToolTip("过滤头像、图标等小图，建议 10~20 KB")
        self.spin_min_size = QSpinBox()
        self.spin_min_size.setRange(1, 10240)
        self.spin_min_size.setSuffix(" KB")
        self.check_min_size.toggled.connect(self.spin_min_size.setEnabled)
        grid.addWidget(self.check_min_size, 2, 0)
        grid.addWidget(QLabel("小于:"), 2, 2)
        grid.addWidget(self.spin_min_size, 2, 3)

        self.check_sequential = QCheckBox("递增编号命名 (001.jpg, 002.jpg…)")
        self.check_sequential.setToolTip("取消勾选则命名为 001_原文件名.jpg")
        self.check_dedupe = QCheckBox("跳过内容重复的图片")
        grid.addWidget(self.check_sequential, 3, 0, 1, 2)
        grid.addWidget(self.check_dedupe, 3, 2, 1, 2)
        grid.setColumnStretch(4, 1)
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

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setFormat("")
        self.progress.setValue(0)
        self.status = QLabel("就绪")
        row.addWidget(self.progress, 1)
        row.addWidget(self.status)
        layout.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        layout.addWidget(self.log, 1)

    def _load_settings(self):
        s = self.settings
        self.output_edit.setText(s.value('output', OUTPUT_DIR))
        self.spin_threads.setValue(int(s.value('threads', NUM_THREADS)))
        self.spin_timeout.setValue(int(s.value('timeout', TIMEOUT)))
        self.check_pagination.setChecked(s.value('pagination', 'true') == 'true')
        self.spin_max_pages.setValue(int(s.value('max_pages', 0)))
        self.check_min_size.setChecked(s.value('min_size_on', 'false') == 'true')
        self.spin_min_size.setValue(int(s.value('min_size', 10)))
        self.check_sequential.setChecked(s.value('sequential', 'true') == 'true')
        self.check_dedupe.setChecked(s.value('dedupe', 'true') == 'true')
        self.spin_max_pages.setEnabled(self.check_pagination.isChecked())
        self.spin_min_size.setEnabled(self.check_min_size.isChecked())

    def _save_settings(self):
        s = self.settings
        s.setValue('output', self.output_edit.text().strip())
        s.setValue('threads', self.spin_threads.value())
        s.setValue('timeout', self.spin_timeout.value())
        s.setValue('pagination', 'true' if self.check_pagination.isChecked() else 'false')
        s.setValue('max_pages', self.spin_max_pages.value())
        s.setValue('min_size_on', 'true' if self.check_min_size.isChecked() else 'false')
        s.setValue('min_size', self.spin_min_size.value())
        s.setValue('sequential', 'true' if self.check_sequential.isChecked() else 'false')
        s.setValue('dedupe', 'true' if self.check_dedupe.isChecked() else 'false')

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _open_output(self):
        path = self.last_output_dir or self.output_edit.text().strip()
        if path and not os.path.isdir(path):
            path = os.path.dirname(path)
        if path and os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _on_start(self):
        if self.worker and self.worker.isRunning():
            return
        url = self.url_edit.text().strip()
        if not url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "提示", "请输入以 http:// 或 https:// 开头的网页地址")
            return
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return
        self._save_settings()

        self.worker = DownloaderWorker(
            url=url, output_dir=output,
            num_threads=self.spin_threads.value(),
            timeout=self.spin_timeout.value(),
            use_sequential_naming=self.check_sequential.isChecked(),
            auto_pagination=self.check_pagination.isChecked(),
            max_pages=self.spin_max_pages.value() or None,
            min_image_size_kb=self.spin_min_size.value() if self.check_min_size.isChecked() else 0,
            dedupe=self.check_dedupe.isChecked(),
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.count.connect(self._on_count)
        self.worker.done.connect(self._on_done)
        self.progress.setRange(0, 0)
        self.status.setText("正在解析网页…")
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.log.appendPlainText(f"\n[+] 开始任务: {url}")
        self.worker.start()

    def _on_count(self, done, total):
        self.progress.setFormat("%v / %m")
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.status.setText("正在下载…")

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.status.setText("正在取消…")
            self.btn_cancel.setEnabled(False)

    def _on_done(self, ok, cancelled, output_dir):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if self.progress.maximum() == 0:
            self.progress.setFormat("")
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
        if output_dir:
            self.last_output_dir = output_dir
        stats = self.worker.downloader.stats
        if cancelled:
            self.status.setText(f"已取消，已保存 {stats['ok']} 张")
        elif ok:
            extra = f"，失败 {stats['failed']} 张" if stats['failed'] else ''
            self.status.setText(f"完成：保存 {stats['ok']} 张{extra}")
        else:
            self.status.setText("没有下载到图片，详见日志")

    def closeEvent(self, event):
        self._save_settings()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(15000)
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    dlg = WebpageDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
