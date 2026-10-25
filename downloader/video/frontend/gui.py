# -*- coding: utf-8 -*-
"""
音视频下载器 - PyQt5 图形界面
"""

import os
import sys

from PyQt5.QtCore import QSettings, Qt, QThread, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog,
                             QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPlainTextEdit, QProgressBar, QPushButton, QRadioButton, QSpinBox,
                             QVBoxLayout)

from backend.common import format_duration
from backend.config import AUDIO_FORMATS, OUTPUT_DIR, QUALITY_FORMATS, TIMEOUT
from backend.core import MediaDownloader
from backend.douyin import DouyinDownloader

QUALITY_LABELS = [
    ('best', "最高画质"), ('2160', "4K"), ('1080', "1080p"), ('720', "720p"),
    ('480', "480p"), ('360', "360p"), ('single', "最佳单文件（无需 ffmpeg）"),
]
AUDIO_LABELS = {'best': "原始格式"}


class Worker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(float, str)
    info = pyqtSignal(dict)
    done = pyqtSignal(bool, bool, str)  # 成功, 是否取消, 保存目录

    def __init__(self, **kwargs):
        super().__init__()
        self.downloader = MediaDownloader(
            progress_callback=self.log.emit,
            progress=lambda f, text: self.progress.emit(-1.0 if f is None else f, text),
            info_callback=self._emit_info, **kwargs)

    def _emit_info(self, info):
        keys = ('title', 'duration', 'uploader', 'view_count', '_type')
        self.info.emit({k: info.get(k) for k in keys})

    def run(self):
        d = self.downloader
        try:
            ok = d.run()
        except Exception as e:
            import traceback
            self.log.emit(f"[!] 出现异常: {e}\n{traceback.format_exc()}")
            ok = False
        self.done.emit(ok, d.cancel_event.is_set(), d.output_dir or '')

    def stop(self):
        self.downloader.cancel()


class MediaDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音视频下载器")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)
        self.resize(800, 640)
        self.settings = QSettings('skills-downloader', 'video')
        self.worker = None
        self.last_output_dir = ''
        self._build_ui()
        self._load_settings()
        self._on_mode_changed()

    # ------------------------------------------------------------ 界面

    def _build_ui(self):
        layout = QVBoxLayout(self)

        box = QGroupBox("下载地址")
        row = QHBoxLayout(box)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("YouTube、Bilibili、抖音、X 等视频地址，回车开始下载")
        self.url_edit.returnPressed.connect(self._on_start)
        row.addWidget(self.url_edit)
        self.btn_info = QPushButton("查看信息")
        self.btn_info.setToolTip("只解析标题、时长等信息，不下载")
        self.btn_info.clicked.connect(lambda: self._start('info'))
        row.addWidget(self.btn_info)
        layout.addWidget(box)

        box = QGroupBox("下载内容")
        grid = QGridLayout(box)
        self.radio_video = QRadioButton("视频")
        self.radio_audio = QRadioButton("仅音频")
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_video)
        self.mode_group.addButton(self.radio_audio)
        self.radio_video.toggled.connect(self._on_mode_changed)
        grid.addWidget(self.radio_video, 0, 0)
        grid.addWidget(QLabel("画质:"), 0, 1)
        self.combo_quality = QComboBox()
        for key, label in QUALITY_LABELS:
            self.combo_quality.addItem(label, key)
        grid.addWidget(self.combo_quality, 0, 2)
        grid.addWidget(QLabel("合并为:"), 0, 3)
        self.combo_merge = QComboBox()
        self.combo_merge.addItems(["mp4", "mkv", "webm"])
        grid.addWidget(self.combo_merge, 0, 4)

        grid.addWidget(self.radio_audio, 1, 0)
        grid.addWidget(QLabel("格式:"), 1, 1)
        self.combo_audio = QComboBox()
        for key in AUDIO_FORMATS:
            self.combo_audio.addItem(AUDIO_LABELS.get(key, key), key)
        grid.addWidget(self.combo_audio, 1, 2)
        self.check_embed = QCheckBox("嵌入封面")
        grid.addWidget(self.check_embed, 1, 3, 1, 2)

        self.check_subtitle = QCheckBox("下载字幕（中/英）")
        self.check_thumbnail = QCheckBox("下载封面图")
        self.check_playlist = QCheckBox("下载整个播放列表")
        grid.addWidget(self.check_subtitle, 2, 0, 1, 2)
        grid.addWidget(self.check_thumbnail, 2, 2)
        grid.addWidget(self.check_playlist, 2, 3, 1, 2)
        grid.setColumnStretch(5, 1)
        layout.addWidget(box)

        box = QGroupBox("输出与网络")
        grid = QGridLayout(box)
        grid.addWidget(QLabel("输出目录:"), 0, 0)
        self.output_edit = QLineEdit()
        grid.addWidget(self.output_edit, 0, 1, 1, 3)
        btn = QPushButton("浏览")
        btn.clicked.connect(self._browse)
        grid.addWidget(btn, 0, 4)

        grid.addWidget(QLabel("代理:"), 1, 0)
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("如 socks5://127.0.0.1:1080，留空不用")
        grid.addWidget(self.proxy_edit, 1, 1)
        grid.addWidget(QLabel("超时(秒):"), 1, 2)
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setRange(10, 600)
        grid.addWidget(self.spin_timeout, 1, 3)

        grid.addWidget(QLabel("Cookie:"), 2, 0)
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("浏览器导出的 cookies.txt（需要登录的视频才用）")
        grid.addWidget(self.cookie_edit, 2, 1, 1, 3)
        btn = QPushButton("浏览")
        btn.clicked.connect(self._browse_cookie)
        grid.addWidget(btn, 2, 4)
        layout.addWidget(box)

        self.info_label = QLabel()
        self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.info_label.setVisible(False)
        layout.addWidget(self.info_label)

        row = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setMinimumHeight(34)
        self.btn_start.setStyleSheet(
            "QPushButton{background:#E91E63;color:white;border:none;border-radius:6px;"
            "padding:6px 20px;font-weight:bold}"
            "QPushButton:hover{background:#C2185B}QPushButton:disabled{background:#ccc;color:#888}")
        self.btn_start.clicked.connect(self._on_start)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_open = QPushButton("打开保存位置")
        self.btn_open.clicked.connect(self._open_output)
        row.addWidget(self.btn_start, 2)
        row.addWidget(self.btn_cancel, 1)
        row.addWidget(self.btn_open, 1)
        layout.addLayout(row)

        row = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.status = QLabel("就绪")
        self.status.setMinimumWidth(320)
        row.addWidget(self.progress, 1)
        row.addWidget(self.status)
        layout.addLayout(row)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(3000)
        layout.addWidget(self.log, 1)

    def _load_settings(self):
        s = self.settings
        self.output_edit.setText(s.value('output', OUTPUT_DIR))
        (self.radio_audio if s.value('mode') == 'audio' else self.radio_video).setChecked(True)
        self._select(self.combo_quality, s.value('quality', 'best'))
        self.combo_merge.setCurrentText(s.value('merge', 'mp4'))
        self._select(self.combo_audio, s.value('audio_format', 'best'))
        self.check_embed.setChecked(s.value('embed', 'false') == 'true')
        self.check_subtitle.setChecked(s.value('subtitle', 'false') == 'true')
        self.check_thumbnail.setChecked(s.value('thumbnail', 'false') == 'true')
        self.proxy_edit.setText(s.value('proxy', ''))
        self.cookie_edit.setText(s.value('cookie', ''))
        self.spin_timeout.setValue(int(s.value('timeout', TIMEOUT)))

    def _save_settings(self):
        s = self.settings
        s.setValue('output', self.output_edit.text().strip())
        s.setValue('mode', 'video' if self.radio_video.isChecked() else 'audio')
        s.setValue('quality', self.combo_quality.currentData())
        s.setValue('merge', self.combo_merge.currentText())
        s.setValue('audio_format', self.combo_audio.currentData())
        for key, check in (('embed', self.check_embed), ('subtitle', self.check_subtitle),
                           ('thumbnail', self.check_thumbnail)):
            s.setValue(key, 'true' if check.isChecked() else 'false')
        s.setValue('proxy', self.proxy_edit.text().strip())
        s.setValue('cookie', self.cookie_edit.text().strip())
        s.setValue('timeout', self.spin_timeout.value())

    @staticmethod
    def _select(combo, data):
        idx = combo.findData(data)
        combo.setCurrentIndex(max(idx, 0))

    def _on_mode_changed(self, *_):
        video = self.radio_video.isChecked()
        for w in (self.combo_quality, self.combo_merge, self.check_subtitle, self.check_thumbnail):
            w.setEnabled(video)
        for w in (self.combo_audio, self.check_embed):
            w.setEnabled(not video)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _browse_cookie(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 Cookie 文件", "", "Cookie 文件 (*.txt);;所有文件 (*)")
        if f:
            self.cookie_edit.setText(f)

    def _open_output(self):
        path = self.last_output_dir or self.output_edit.text().strip()
        while path and not os.path.isdir(path):
            parent = os.path.dirname(path)
            path = '' if parent == path else parent
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def _show_info(self, info, error=False):
        if error:
            self.info_label.setStyleSheet("color:#C62828;padding:6px;background:#FFEBEE;border-radius:4px")
            self.info_label.setText(info)
        else:
            self.info_label.setStyleSheet("color:#0D47A1;padding:6px;background:#E3F2FD;border-radius:4px")
            parts = [f"标题: {info.get('title') or 'N/A'}"]
            if info.get('_type') == 'playlist':
                parts.append("类型: 播放列表")
            else:
                parts.append(f"时长: {format_duration(info.get('duration'))}")
            if info.get('uploader'):
                parts.append(f"作者: {info['uploader']}")
            if info.get('view_count') is not None:
                parts.append(f"播放: {info['view_count']}")
            self.info_label.setText("   |   ".join(parts))
        self.info_label.setVisible(True)

    # ------------------------------------------------------------ 任务

    def _on_start(self):
        self._start('video' if self.radio_video.isChecked() else 'audio')

    def _start(self, mode):
        if self.worker and self.worker.isRunning():
            return
        url = self.url_edit.text().strip()
        if not url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "提示", "请输入以 http:// 或 https:// 开头的视频地址")
            return
        output = self.output_edit.text().strip()
        if mode != 'info' and not output:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return
        if DouyinDownloader.is_douyin_url(url) and DouyinDownloader.classify_url(url) == 'user':
            QMessageBox.warning(self, "提示", "这是抖音用户主页，无法批量下载。\n\n"
                                "请在抖音 App 中打开单个视频 → 分享 → 复制链接。")
            return
        cookie = self.cookie_edit.text().strip()
        if cookie and not os.path.isfile(cookie):
            QMessageBox.warning(self, "提示", f"Cookie 文件不存在:\n{cookie}")
            return
        self._save_settings()

        self.worker = Worker(
            url=url, output_dir=output or OUTPUT_DIR, mode=mode,
            format_spec=QUALITY_FORMATS[self.combo_quality.currentData()],
            merge_output_format=self.combo_merge.currentText(),
            audio_format=self.combo_audio.currentData(),
            download_subtitle=self.check_subtitle.isChecked(),
            download_thumbnail=self.check_thumbnail.isChecked(),
            download_playlist=self.check_playlist.isChecked(),
            embed_thumbnail=self.check_embed.isChecked(),
            proxy=self.proxy_edit.text().strip() or None,
            cookie_file=cookie or None,
            timeout=self.spin_timeout.value(),
        )
        self.worker.log.connect(self.log.appendPlainText)
        self.worker.progress.connect(self._on_progress)
        self.worker.info.connect(self._show_info)
        self.worker.done.connect(self._on_done)
        self.info_label.setVisible(False)
        self.progress.setRange(0, 0)
        self.status.setText("正在解析…")
        self.btn_start.setEnabled(False)
        self.btn_info.setEnabled(False)
        self.btn_cancel.setEnabled(mode != 'info')
        self.log.appendPlainText(f"\n[+] {'查看信息' if mode == 'info' else '开始下载'}: {url}")
        self.worker.start()

    def _on_progress(self, fraction, text):
        if fraction < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 1000)
            self.progress.setValue(int(fraction * 1000))
        self.status.setText(text[:60])

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.status.setText("正在取消…")
            self.btn_cancel.setEnabled(False)

    def _on_done(self, ok, cancelled, output_dir):
        self.btn_start.setEnabled(True)
        self.btn_info.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.progress.setRange(0, 1000)
        d = self.worker.downloader
        if output_dir:
            self.last_output_dir = output_dir
        if d.mode == 'info':
            self.progress.setValue(0)
            self.status.setText("信息获取完成" if ok else "获取信息失败")
            if not ok:
                self._show_info("获取信息失败，详见日志", error=True)
        elif cancelled:
            self.status.setText("已取消")
        elif ok:
            self.progress.setValue(1000)
            self.status.setText(f"完成：保存 {d.downloaded_count} 个文件")
        else:
            self.progress.setValue(0)
            self.status.setText("下载失败，详见日志")

    def closeEvent(self, event):
        self._save_settings()
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(15000)
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle('Fusion')
    dlg = MediaDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())
