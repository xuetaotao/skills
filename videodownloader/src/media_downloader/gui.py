# -*- coding: utf-8 -*-
"""
音视频下载工具 - PyQt5 GUI

提供视频/音频下载的图形界面，支持格式选择、代理设置等。
"""

import sys
import os
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QSpinBox, QFileDialog,
                             QPlainTextEdit, QMessageBox, QCheckBox, QComboBox,
                             QGroupBox, QTabWidget, QWidget, QRadioButton,
                             QButtonGroup)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from .core import MediaDownloader


class DownloaderWorker(QThread):
    progress = pyqtSignal(str)
    info_ready = pyqtSignal(dict)
    finished = pyqtSignal(bool)

    def __init__(self, url, output_dir, mode, format_spec, merge_output_format,
                 audio_format, audio_quality, download_subtitle, download_thumbnail,
                 download_playlist, embed_thumbnail, proxy, cookie_file, timeout,
                 parent=None):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.mode = mode
        self.format_spec = format_spec
        self.merge_output_format = merge_output_format
        self.audio_format = audio_format
        self.audio_quality = audio_quality
        self.download_subtitle = download_subtitle
        self.download_thumbnail = download_thumbnail
        self.download_playlist = download_playlist
        self.embed_thumbnail = embed_thumbnail
        self.proxy = proxy
        self.cookie_file = cookie_file
        self.timeout = timeout
        self._is_stopped = False

    def run(self):
        try:
            downloader = MediaDownloader(
                url=self.url,
                output_dir=self.output_dir,
                mode=self.mode,
                format_spec=self.format_spec,
                merge_output_format=self.merge_output_format,
                audio_format=self.audio_format,
                audio_quality=self.audio_quality,
                download_subtitle=self.download_subtitle,
                download_thumbnail=self.download_thumbnail,
                download_playlist=self.download_playlist,
                embed_thumbnail=self.embed_thumbnail,
                proxy=self.proxy if self.proxy else None,
                cookie_file=self.cookie_file if self.cookie_file else None,
                timeout=self.timeout,
            )

            success = downloader.run_with_info_callback(
                info_callback=self._on_info_ready,
                progress_callback=self._on_progress,
            )
            self.finished.emit(success)

        except Exception as e:
            self.progress.emit(f"[!] 出现异常: {e}")
            import traceback
            self.progress.emit(traceback.format_exc())
            self.finished.emit(False)

    def _on_info_ready(self, info):
        self.info_ready.emit(info)

    def _on_progress(self, msg):
        if self._is_stopped:
            # yt-dlp 不支持优雅停止，但我们可以标记
            pass
        self.progress.emit(msg)

    def stop(self):
        self._is_stopped = True


class InfoWorker(QThread):
    """获取视频信息的工作线程"""
    info_ready = pyqtSignal(dict)
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, url, proxy=None, cookie_file=None, parent=None):
        super().__init__(parent)
        self.url = url
        self.proxy = proxy
        self.cookie_file = cookie_file

    def run(self):
        try:
            self.progress.emit(f"[*] 正在获取信息: {self.url}")
            downloader = MediaDownloader(
                url=self.url,
                output_dir='./output',
                mode='info',
                proxy=self.proxy if self.proxy else None,
                cookie_file=self.cookie_file if self.cookie_file else None,
            )
            info = downloader.fetch_info()
            if info:
                self.info_ready.emit(info)
                self.finished.emit(True)
            else:
                self.progress.emit("[-] 无法获取信息")
                self.finished.emit(False)
        except Exception as e:
            self.progress.emit(f"[-] 获取信息失败: {e}")
            self.finished.emit(False)


class MediaDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("音视频下载器")
        self.resize(750, 600)
        self.worker = None
        self.info_worker = None
        self._current_info = None

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout()

        # URL 输入
        url_group = QGroupBox("下载地址")
        url_layout = QHBoxLayout()
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("输入视频/音频地址 (YouTube, Bilibili, 等)")
        url_layout.addWidget(self.url_edit)

        self.btn_info = QPushButton("查看信息")
        self.btn_info.setToolTip("获取视频/音频的详细信息（不下载）")
        self.btn_info.clicked.connect(self._on_fetch_info)
        url_layout.addWidget(self.btn_info)

        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        # 下载模式选择
        mode_group = QGroupBox("下载模式")
        mode_layout = QHBoxLayout()
        self.radio_video = QRadioButton("下载视频")
        self.radio_audio = QRadioButton("下载音频")
        self.radio_video.setChecked(True)
        self.mode_btn_group = QButtonGroup()
        self.mode_btn_group.addButton(self.radio_video, 0)
        self.mode_btn_group.addButton(self.radio_audio, 1)
        self.mode_btn_group.buttonClicked.connect(self._on_mode_changed)
        mode_layout.addWidget(self.radio_video)
        mode_layout.addWidget(self.radio_audio)
        mode_layout.addStretch()

        # 视频格式选择
        mode_layout.addWidget(QLabel("视频画质:"))
        self.combo_video_format = QComboBox()
        self.combo_video_format.addItems([
            "最高画质 (bestvideo+bestaudio)",
            "1080p",
            "720p",
            "480p",
            "360p",
            "最佳单文件 (best)",
        ])
        self.combo_video_format.setCurrentIndex(0)
        self.combo_video_format.currentIndexChanged.connect(self._on_video_format_changed)
        mode_layout.addWidget(self.combo_video_format)

        # 合并格式
        mode_layout.addWidget(QLabel("合并为:"))
        self.combo_merge_format = QComboBox()
        self.combo_merge_format.addItems(["mp4", "mkv", "webm"])
        self.combo_merge_format.setCurrentIndex(0)
        mode_layout.addWidget(self.combo_merge_format)

        # 音频格式选择
        mode_layout.addWidget(QLabel("音频格式:"))
        self.combo_audio_format = QComboBox()
        self.combo_audio_format.addItems(["最佳原始格式", "mp3", "m4a", "flac", "wav", "aac", "opus"])
        self.combo_audio_format.setCurrentIndex(0)
        self.combo_audio_format.setEnabled(False)
        mode_layout.addWidget(self.combo_audio_format)

        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # 输出目录和选项
        opt_group = QGroupBox("输出与选项")
        opt_layout = QVBoxLayout()

        # 输出目录
        row = QHBoxLayout()
        row.addWidget(QLabel("输出目录:"))
        self.output_edit = QLineEdit(os.path.join(os.getcwd(), "output"))
        row.addWidget(self.output_edit)
        self.btn_browse = QPushButton("浏览")
        self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.btn_browse)
        opt_layout.addLayout(row)

        # 选项行
        row2 = QHBoxLayout()

        self.check_subtitle = QCheckBox("下载字幕")
        self.check_subtitle.setChecked(False)
        row2.addWidget(self.check_subtitle)

        self.check_thumbnail = QCheckBox("下载缩略图")
        self.check_thumbnail.setChecked(False)
        row2.addWidget(self.check_thumbnail)

        self.check_embed_thumbnail = QCheckBox("嵌入缩略图(音频)")
        self.check_embed_thumbnail.setChecked(False)
        self.check_embed_thumbnail.setEnabled(False)
        row2.addWidget(self.check_embed_thumbnail)

        self.check_playlist = QCheckBox("下载播放列表")
        self.check_playlist.setChecked(False)
        row2.addWidget(self.check_playlist)

        row2.addStretch()
        opt_layout.addLayout(row2)

        # 代理和 Cookie
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("代理:"))
        self.proxy_edit = QLineEdit()
        self.proxy_edit.setPlaceholderText("如 socks5://127.0.0.1:1080")
        row3.addWidget(self.proxy_edit)

        row3.addWidget(QLabel("Cookie:"))
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setPlaceholderText("Cookie 文件路径")
        row3.addWidget(self.cookie_edit)
        self.btn_cookie_browse = QPushButton("浏览")
        self.btn_cookie_browse.clicked.connect(self._browse_cookie)
        row3.addWidget(self.btn_cookie_browse)

        opt_layout.addLayout(row3)

        # 超时
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("超时(秒):"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setMinimum(10)
        self.spin_timeout.setMaximum(600)
        self.spin_timeout.setValue(30)
        row4.addWidget(self.spin_timeout)
        row4.addStretch()
        opt_layout.addLayout(row4)

        opt_group.setLayout(opt_layout)
        layout.addWidget(opt_group)

        # 信息展示区
        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: #1565C0; padding: 4px; background: #E3F2FD; border-radius: 4px;")
        self.info_label.setVisible(False)
        layout.addWidget(self.info_label)

        # 操作按钮
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.setMinimumHeight(36)
        self.btn_start.setStyleSheet("""
            QPushButton {
                background-color: #E91E63; color: white;
                border: none; border-radius: 6px; padding: 8px 20px;
                font-weight: bold; font-size: 13px;
            }
            QPushButton:hover { background-color: #C2185B; }
            QPushButton:pressed { background-color: #AD1457; }
            QPushButton:disabled { background-color: #ccc; color: #999; }
        """)
        self.btn_start.clicked.connect(self._on_start)
        btn_row.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        btn_row.addWidget(self.btn_close)

        layout.addLayout(btn_row)

        # 日志区域
        layout.addWidget(QLabel("日志:"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(500)
        layout.addWidget(self.log, 1)

        self.setLayout(layout)

    def _on_mode_changed(self, btn):
        is_video = self.radio_video.isChecked()
        self.combo_video_format.setEnabled(is_video)
        self.combo_merge_format.setEnabled(is_video)
        self.check_subtitle.setEnabled(is_video)
        self.check_thumbnail.setEnabled(is_video)
        self.combo_audio_format.setEnabled(not is_video)
        self.check_embed_thumbnail.setEnabled(not is_video)

    def _on_video_format_changed(self, index):
        pass  # 格式映射在 _on_start 中处理

    def _get_format_spec(self):
        """根据用户选择返回 yt-dlp 格式字符串"""
        idx = self.combo_video_format.currentIndex()
        format_map = {
            0: 'bestvideo+bestaudio/best',    # 最高画质
            1: 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',  # 1080p
            2: 'bestvideo[height<=720]+bestaudio/best[height<=720]',    # 720p
            3: 'bestvideo[height<=480]+bestaudio/best[height<=480]',    # 480p
            4: 'bestvideo[height<=360]+bestaudio/best[height<=360]',    # 360p
            5: 'best',                       # 最佳单文件
        }
        return format_map.get(idx, 'bestvideo+bestaudio/best')

    def _get_audio_format(self):
        """根据用户选择返回音频格式"""
        idx = self.combo_audio_format.currentIndex()
        format_map = {
            0: 'best',    # 最佳原始格式
            1: 'mp3',
            2: 'm4a',
            3: 'flac',
            4: 'wav',
            5: 'aac',
            6: 'opus',
        }
        return format_map.get(idx, 'best')

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _browse_cookie(self):
        f, _ = QFileDialog.getOpenFileName(self, "选择 Cookie 文件", "", "All Files (*)")
        if f:
            self.cookie_edit.setText(f)

    def _on_fetch_info(self):
        """获取视频信息"""
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先输入地址")
            return

        self.btn_info.setEnabled(False)
        self.info_label.setText("正在获取信息...")
        self.info_label.setVisible(True)

        proxy = self.proxy_edit.text().strip() or None
        cookie = self.cookie_edit.text().strip() or None

        self.info_worker = InfoWorker(url, proxy, cookie)
        self.info_worker.info_ready.connect(self._on_info_received)
        self.info_worker.progress.connect(self._append_log)
        self.info_worker.finished.connect(self._on_info_finished)
        self.info_worker.start()

    def _on_info_received(self, info):
        self._current_info = info
        title = info.get('title', 'N/A')
        duration = info.get('duration', 0)
        duration_str = f"{int(duration // 60)}:{int(duration % 60):02d}" if duration else "N/A"
        uploader = info.get('uploader', 'N/A')
        view_count = info.get('view_count', 'N/A')

        text = f"标题: {title}  |  时长: {duration_str}  |  上传者: {uploader}  |  播放量: {view_count}"
        self.info_label.setText(text)
        self.info_label.setVisible(True)

    def _on_info_finished(self, success):
        self.btn_info.setEnabled(True)
        if not success and not self._current_info:
            self.info_label.setText("获取信息失败")
            self.info_label.setStyleSheet("color: #C62828; padding: 4px; background: #FFEBEE; border-radius: 4px;")
        else:
            self.info_label.setStyleSheet("color: #1565C0; padding: 4px; background: #E3F2FD; border-radius: 4px;")

    def _append_log(self, text):
        self.log.appendPlainText(text)

    def _on_start(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先输入视频/音频地址")
            return
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return

        # 抖音链接提示
        from .douyin import DouyinDownloader
        if DouyinDownloader.is_douyin_url(url):
            url_type = DouyinDownloader.classify_url(url)
            if url_type == 'user':
                # 用户主页链接需要 modal_id
                QMessageBox.warning(
                    self, "提示",
                    "检测到抖音用户主页链接。\n\n"
                    "抖音用户主页无法直接批量下载，请提供单个视频链接。\n\n"
                    "提示：在抖音 App 中打开视频 → 分享 → 复制链接"
                )
                return
            self._append_log("[*] 检测到抖音链接，将使用抖音专用下载器（无水印）")

        mode = 'video' if self.radio_video.isChecked() else 'audio'
        format_spec = self._get_format_spec()
        merge_format = self.combo_merge_format.currentText()
        audio_format = self._get_audio_format()
        proxy = self.proxy_edit.text().strip() or None
        cookie = self.cookie_edit.text().strip() or None

        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.btn_info.setEnabled(False)
        self._append_log(f"\n[+] 已启动下载任务: {url}")

        self.worker = DownloaderWorker(
            url=url, output_dir=output, mode=mode,
            format_spec=format_spec, merge_output_format=merge_format,
            audio_format=audio_format, audio_quality='0',
            download_subtitle=self.check_subtitle.isChecked(),
            download_thumbnail=self.check_thumbnail.isChecked(),
            download_playlist=self.check_playlist.isChecked(),
            embed_thumbnail=self.check_embed_thumbnail.isChecked(),
            proxy=proxy, cookie_file=cookie,
            timeout=self.spin_timeout.value(),
        )
        self.worker.progress.connect(self._append_log)
        self.worker.info_ready.connect(self._on_info_received)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self._append_log("[!] 请求取消中... (yt-dlp 会在当前下载完成后停止)")
            self.btn_cancel.setEnabled(False)

    def _on_finished(self, success):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        self.btn_info.setEnabled(True)
        if success:
            QMessageBox.information(self, "完成", "下载完成！")
        else:
            QMessageBox.information(self, "结束", "下载结束（可能失败或被取消）")


def main():
    app = QApplication(sys.argv)
    dlg = MediaDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    main()
