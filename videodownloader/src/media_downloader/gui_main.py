# -*- coding: utf-8 -*-
"""
音视频下载器 - GUI入口
"""

import sys
from PyQt5.QtWidgets import QApplication
from .gui import MediaDownloaderDialog


def main():
    app = QApplication(sys.argv)
    dlg = MediaDownloaderDialog()
    dlg.show()
    return app.exec_()


if __name__ == '__main__':
    main()
