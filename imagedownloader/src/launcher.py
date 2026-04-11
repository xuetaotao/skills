#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
网页图片下载工具 - GUI 启动入口
"""

import sys
import os
import subprocess

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QPushButton, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class LauncherWindow(QMainWindow):
    """启动器主窗口"""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("网页图片下载器")
        self.setGeometry(100, 100, 500, 300)
        self.init_ui()

    def init_ui(self):
        """初始化 UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(40, 40, 40, 40)

        # 标题
        title = QLabel("🌐  网页图片下载器")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)

        # 描述
        desc = QLabel("从指定网页批量下载所有图片")
        desc_font = QFont()
        desc_font.setPointSize(11)
        desc.setFont(desc_font)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #666;")
        main_layout.addWidget(desc)

        main_layout.addSpacing(20)

        # 启动按钮
        btn = QPushButton("🚀  启动下载器")
        btn.setMinimumHeight(80)
        btn_font = QFont()
        btn_font.setPointSize(12)
        btn_font.setBold(True)
        btn.setFont(btn_font)
        btn.setToolTip("从指定网页批量下载所有图片")
        btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:pressed {
                background-color: #0a66b8;
            }
        """)
        btn.clicked.connect(self.launch_downloader)
        main_layout.addWidget(btn)

        main_layout.addSpacing(20)
        footer = QLabel("💡 提示: 也可以通过命令行使用，运行 python -m src --help 查看帮助")
        footer_font = QFont()
        footer_font.setPointSize(9)
        footer.setFont(footer_font)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999;")
        main_layout.addWidget(footer)

        central_widget.setLayout(main_layout)

    def launch_downloader(self):
        """启动网页图片下载器"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            subprocess.Popen([sys.executable, '-m', 'src.webpage_downloader.gui_main'],
                             cwd=project_root)
            self.close()
        except Exception as e:
            print(f"[-] 无法启动网页图片下载器: {e}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"无法启动网页图片下载器:\n{e}")


def main():
    """主函数"""
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    launcher = LauncherWindow()
    launcher.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
