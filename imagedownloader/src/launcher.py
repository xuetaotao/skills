#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一启动器 - 方便快速启动图片下载器的两个 GUI
"""

import sys
import os
import subprocess

from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QPushButton, QLabel)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont


class LauncherWindow(QMainWindow):
    """启动器主窗口"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("图片下载器 - 启动器")
        self.setGeometry(100, 100, 600, 400)
        self.init_ui()
    
    def init_ui(self):
        """初始化 UI"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(40, 40, 40, 40)
        
        # 标题
        title = QLabel("🖼️  图片下载工具启动器")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # 描述
        desc = QLabel("选择一个下载工具开始使用")
        desc_font = QFont()
        desc_font.setPointSize(11)
        desc.setFont(desc_font)
        desc.setAlignment(Qt.AlignCenter)
        desc.setStyleSheet("color: #666;")
        main_layout.addWidget(desc)
        
        main_layout.addSpacing(20)
        
        # 按钮
        button_layout = QVBoxLayout()
        button_layout.setSpacing(15)
        
        btn1 = QPushButton("🔍  图片搜索下载器")
        btn1.setMinimumHeight(80)
        btn1_font = QFont()
        btn1_font.setPointSize(12)
        btn1_font.setBold(True)
        btn1.setFont(btn1_font)
        btn1.setToolTip("从 Google、Bing、百度搜索引擎下载图片")
        btn1.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        btn1.clicked.connect(self.launch_search_downloader)
        button_layout.addWidget(btn1)
        
        btn2 = QPushButton("🌐  网页图片下载器")
        btn2.setMinimumHeight(80)
        btn2_font = QFont()
        btn2_font.setPointSize(12)
        btn2_font.setBold(True)
        btn2.setFont(btn2_font)
        btn2.setToolTip("从指定网页批量下载所有图片")
        btn2.setStyleSheet("""
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
        btn2.clicked.connect(self.launch_webpage_downloader)
        button_layout.addWidget(btn2)
        
        main_layout.addLayout(button_layout)
        
        main_layout.addSpacing(20)
        footer = QLabel("💡 提示: 也可以通过命令行使用，运行 python -m src --help 查看帮助")
        footer_font = QFont()
        footer_font.setPointSize(9)
        footer.setFont(footer_font)
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: #999;")
        main_layout.addWidget(footer)
        
        central_widget.setLayout(main_layout)
    
    def launch_search_downloader(self):
        """启动图片搜索下载器"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            subprocess.Popen([sys.executable, '-m', 'src.search_downloader.gui'],
                           cwd=project_root)
            self.close()
        except Exception as e:
            print(f"[-] 无法启动图片搜索下载器: {e}")
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"无法启动图片搜索下载器:\n{e}")
    
    def launch_webpage_downloader(self):
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
