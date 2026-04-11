# -*- coding: utf-8 -*-
"""
A simple PyQt5 GUI for the webpage_image_downloader tool.

Provides inputs for URL, output directory, threads and timeout.
Runs the downloader in a background QThread and streams simple logs to the UI.
"""

import sys
import os
from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QSpinBox, QFileDialog,
                             QPlainTextEdit, QMessageBox, QCheckBox)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from .core import WebpageImageDownloader


class DownloaderWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool)

    def __init__(self, url, output_dir, num_threads, timeout, use_sequential_naming=True, 
                 auto_pagination=True, max_pages=None, parent=None):
        super().__init__(parent)
        self.url = url
        self.output_dir = output_dir
        self.num_threads = num_threads
        self.timeout = timeout
        self.use_sequential_naming = use_sequential_naming
        self.auto_pagination = auto_pagination
        self.max_pages = max_pages
        self._is_stopped = False

    def run(self):
        try:
            downloader = WebpageImageDownloader(
                self.url, 
                self.output_dir, 
                self.num_threads, 
                self.timeout,
                use_sequential_naming=self.use_sequential_naming,
                auto_pagination=self.auto_pagination,
                max_pages=self.max_pages
            )

            # 使用多页下载逻辑（支持自动翻页）
            current_url = self.url
            page_count = 0
            total_downloaded = 0
            first_html = None
            
            while True:
                if self._is_stopped:
                    self.progress.emit("[!] 已取消")
                    self.finished.emit(False)
                    return
                
                page_count += 1
                self.progress.emit(f"\n[*] 正在处理第 {page_count} 页...")
                
                # 获取当前页面的 HTML
                self.progress.emit(f"[+] 请求网页: {current_url}")
                html = downloader.fetch_webpage()
                if not html:
                    self.progress.emit("[-] 获取网页失败")
                    break
                
                # 保存第一页 HTML 用于生成子目录名
                if first_html is None:
                    first_html = html
                
                # 提取图片 URL
                self.progress.emit("[+] 解析图片 URL...")
                downloader.url = current_url  # 更新当前 URL
                image_urls = downloader.extract_image_urls(html)
                
                if len(image_urls) == 0:
                    self.progress.emit("[-] 未发现图片，停止下载")
                    break
                
                self.progress.emit(f"[+] 第 {page_count} 页找到 {len(image_urls)} 张图片")
                
                # 第一次获取到图片时，生成子目录并更新下载器的输出目录
                if total_downloaded == 0:
                    subdir_name = downloader.generate_subdir_name(self.url, first_html)
                    downloader.output_dir = os.path.join(self.output_dir, subdir_name)
                    os.makedirs(downloader.output_dir, exist_ok=True)
                    self.progress.emit(f"[+] 输出目录: {os.path.abspath(downloader.output_dir)}")
                
                # 下载当前页面的所有图片
                # 关键：使用全局计数器 downloader.index_counter 来保持编号连续性
                for relative_index, url in enumerate(image_urls):
                    if self._is_stopped:
                        self.progress.emit("[!] 已取消")
                        self.finished.emit(False)
                        return
                    
                    # 使用全局计数器保持编号连续
                    global_index = downloader.index_counter + relative_index
                    filename = downloader.get_image_filename(url, global_index)
                    ok = downloader.download_image(url, filename)
                    total_downloaded += 1
                    status = '✓' if ok else '✗'
                    self.progress.emit(f"[{total_downloaded}] {status} {filename}")
                
                # 更新计数器
                downloader.index_counter += len(image_urls)
                
                # 检查是否需要继续翻页
                if not self.auto_pagination:
                    self.progress.emit("[+] 自动翻页已禁用，停止下载")
                    break
                
                # 检查是否达到最大页数限制
                if self.max_pages and page_count >= self.max_pages:
                    self.progress.emit(f"[+] 已到达最大页数限制 ({self.max_pages} 页)，停止下载")
                    break
                
                # 查找下一页的 URL
                self.progress.emit("[*] 查找下一页链接...")
                next_url = downloader.find_next_page_url(html, current_url)
                
                if not next_url:
                    self.progress.emit("[+] 没有找到下一页链接，下载完成")
                    break
                
                self.progress.emit(f"[+] 找到下一页: {next_url}")
                current_url = next_url
            
            self.progress.emit(f"\n[+] 下载完成！总共下载 {total_downloaded} 张图片")
            self.finished.emit(True)

        except Exception as e:
            self.progress.emit(f"[!] 出现异常: {e}")
            import traceback
            self.progress.emit(traceback.format_exc())
            self.finished.emit(False)

    def stop(self):
        self._is_stopped = True


class WebpageDownloaderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("网页图片下载器")
        self.resize(700, 480)

        self._build_ui()
        self.worker = None

    def _build_ui(self):
        layout = QVBoxLayout()

        # URL
        row = QHBoxLayout()
        row.addWidget(QLabel("网页 URL:"))
        self.url_edit = QLineEdit()
        row.addWidget(self.url_edit)
        layout.addLayout(row)

        # output dir
        row = QHBoxLayout()
        row.addWidget(QLabel("输出目录:"))
        self.output_edit = QLineEdit(os.path.join(os.getcwd(), "output"))
        row.addWidget(self.output_edit)
        self.btn_browse = QPushButton("浏览")
        self.btn_browse.clicked.connect(self._browse)
        row.addWidget(self.btn_browse)
        layout.addLayout(row)

        # threads and timeout
        row = QHBoxLayout()
        row.addWidget(QLabel("线程数:"))
        self.spin_threads = QSpinBox()
        self.spin_threads.setMinimum(1)
        self.spin_threads.setMaximum(32)
        self.spin_threads.setValue(8)
        row.addWidget(self.spin_threads)

        row.addWidget(QLabel("超时(s):"))
        self.spin_timeout = QSpinBox()
        self.spin_timeout.setMinimum(5)
        self.spin_timeout.setMaximum(300)
        self.spin_timeout.setValue(30)
        row.addWidget(self.spin_timeout)

        layout.addLayout(row)

        # naming option
        row = QHBoxLayout()
        self.check_sequential = QCheckBox("使用递增编号 (001.jpg, 002.jpg, ...)")
        self.check_sequential.setChecked(True)
        self.check_sequential.setToolTip("勾选使用递增编号命名，避免重名\n取消勾选则保留原文件名")
        row.addWidget(self.check_sequential)
        layout.addLayout(row)

        # pagination option
        row = QHBoxLayout()
        self.check_auto_pagination = QCheckBox("自动翻页下载 (默认启用)")
        self.check_auto_pagination.setChecked(True)
        self.check_auto_pagination.setToolTip("勾选将自动翻页并下载所有页面的图片")
        self.check_auto_pagination.stateChanged.connect(self._on_pagination_toggled)
        row.addWidget(self.check_auto_pagination)
        
        row.addWidget(QLabel("最多页数:"))
        self.spin_max_pages = QSpinBox()
        self.spin_max_pages.setMinimum(0)  # 0 表示无限制
        self.spin_max_pages.setMaximum(9999)
        self.spin_max_pages.setValue(0)  # 默认无限制
        self.spin_max_pages.setEnabled(True)
        row.addWidget(self.spin_max_pages)
        
        row.addWidget(QLabel("(0=无限制)"))
        layout.addLayout(row)

        # buttons
        row = QHBoxLayout()
        self.btn_start = QPushButton("开始下载")
        self.btn_start.clicked.connect(self._on_start)
        row.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.setEnabled(False)
        row.addWidget(self.btn_cancel)

        self.btn_close = QPushButton("关闭")
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)

        layout.addLayout(row)

        # log area
        layout.addWidget(QLabel("日志:"))
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.log, 1)

        self.setLayout(layout)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_edit.text())
        if d:
            self.output_edit.setText(d)

    def _append_log(self, text):
        self.log.appendPlainText(text)

    def _on_pagination_toggled(self):
        """翻页复选框状态改变时的回调"""
        is_checked = self.check_auto_pagination.isChecked()
        self.spin_max_pages.setEnabled(is_checked)

    def _on_start(self):
        url = self.url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请先输入网页 URL")
            return
        output = self.output_edit.text().strip()
        if not output:
            QMessageBox.warning(self, "提示", "请先选择输出目录")
            return

        num_threads = int(self.spin_threads.value())
        timeout = int(self.spin_timeout.value())
        use_sequential = self.check_sequential.isChecked()
        auto_pagination = self.check_auto_pagination.isChecked()
        max_pages_value = int(self.spin_max_pages.value())
        max_pages = None if max_pages_value == 0 else max_pages_value

        # disable start, enable cancel
        self.btn_start.setEnabled(False)
        self.btn_cancel.setEnabled(True)

        # create worker
        self.worker = DownloaderWorker(url, output, num_threads, timeout, use_sequential, 
                                       auto_pagination, max_pages)
        self.worker.progress.connect(self._append_log)
        self.worker.finished.connect(self._on_finished)
        self.worker.start()
        self._append_log(f"[+] 已启动下载任务: {url}")

    def _on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self._append_log("[!] 请求取消中...")
            self.btn_cancel.setEnabled(False)

    def _on_finished(self, success):
        self.btn_start.setEnabled(True)
        self.btn_cancel.setEnabled(False)
        if success:
            QMessageBox.information(self, "完成", "下载完成！")
        else:
            QMessageBox.information(self, "结束", "下载结束（可能失败或被取消）")


def main():
    app = QApplication(sys.argv)
    dlg = WebpageDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    main()
