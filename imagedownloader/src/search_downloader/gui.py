# -*- coding: utf-8 -*-
"""
搜索引擎图片下载器 - GUI入口
"""

import sys
from PyQt5.Qt import QApplication
from .mainwindow import MainWindow
from .logger import logger


def main():
    app = QApplication(sys.argv)
    
    logger.initialize()

    font = app.font()
    if sys.platform.startswith("win"):
        font.setFamily("Microsoft YaHei")
    else:
        font.setFamily("Ubuntu")
    app.setFont(font)

    main_window = MainWindow()
    main_window.setWindowTitle("图片搜索下载器")
    main_window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
