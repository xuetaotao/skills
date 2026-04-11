# -*- coding: utf-8 -*-
"""
网页图片下载器 - GUI入口
"""

import sys
from PyQt5.QtWidgets import QApplication
from .gui import WebpageDownloaderDialog


def main():
    app = QApplication(sys.argv)
    dlg = WebpageDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    main()
