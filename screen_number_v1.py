import sys
import time
import mss
import cv2
import numpy as np
import easyocr

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QPushButton,
    QLabel,
    QVBoxLayout,
    QHBoxLayout
)

from PyQt5.QtGui import (
    QPixmap,
    QImage
)

from PyQt5.QtCore import Qt


# =========================
# OCR初始化
# =========================

print("正在加载OCR模型...")

reader = easyocr.Reader(
    ['en'],
    gpu=False
)

print("OCR加载完成")


# =========================
# 框选窗口
# =========================

class SelectArea(QWidget):

    def __init__(self):
        super().__init__()

        self.begin = None
        self.end = None

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint
        )

        self.setWindowOpacity(0.3)

        self.setStyleSheet(
            "background-color:blue;"
        )

        screen = QApplication.primaryScreen()
        size = screen.size()

        self.setGeometry(
            0,
            0,
            size.width(),
            size.height()
        )

    def mousePressEvent(self,event):

        if event.button()==Qt.LeftButton:

            self.begin = event.pos()
            self.end = self.begin


    def mouseMoveEvent(self,event):

        if self.begin:

            self.end = event.pos()

            self.update()


    def mouseReleaseEvent(self,event):

        if self.begin:

            self.end = event.pos()

            self.close()


    def paintEvent(self,event):

        if self.begin and self.end:

            from PyQt5.QtGui import QPainter,QPen

            painter=QPainter(self)

            pen=QPen(
                Qt.red,
                3
            )

            painter.setPen(pen)

            painter.drawRect(
                self.begin.x(),
                self.begin.y(),
                self.end.x()-self.begin.x(),
                self.end.y()-self.begin.y()
            )


    def get_rect(self):

        x1=self.begin.x()
        y1=self.begin.y()

        x2=self.end.x()
        y2=self.end.y()


        return (
            min(x1,x2),
            min(y1,y2),
            abs(x2-x1),
            abs(y2-y1)
        )



# =========================
# 主程序
# =========================


class MainWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "屏幕数字识别 V1"
        )

        self.resize(
            600,
            500
        )


        self.area=None


        self.info=QLabel(
            "识别区域：未选择"
        )


        self.result=QLabel(
            "识别数字："
        )


        self.image=QLabel()

        self.image.setFixedSize(
            300,
            150
        )


        self.btn_select=QPushButton(
            "框选识别区域"
        )

        self.btn_test=QPushButton(
            "点击测试识别"
        )


        self.btn_select.clicked.connect(
            self.select_area
        )


        self.btn_test.clicked.connect(
            self.test_ocr
        )


        layout=QVBoxLayout()


        layout.addWidget(
            self.btn_select
        )

        layout.addWidget(
            self.info
        )

        layout.addWidget(
            self.btn_test
        )

        layout.addWidget(
            self.image
        )

        layout.addWidget(
            self.result
        )


        self.setLayout(layout)



    # 框选

    def select_area(self):

        self.selector=SelectArea()

        self.selector.show()

        self.selector.closeEvent=self.area_closed



    def area_closed(self,event):

        self.area=self.selector.get_rect()


        self.info.setText(
            f"区域:{self.area}"
        )



    # OCR测试

    def test_ocr(self):

        if not self.area:

            self.result.setText(
                "请先选择区域"
            )

            return


        x,y,w,h=self.area


        with mss.mss() as sct:


            monitor={
                "left":x,
                "top":y,
                "width":w,
                "height":h
            }


            img=sct.grab(
                monitor
            )


            img=np.array(img)


        img=cv2.cvtColor(
            img,
            cv2.COLOR_BGRA2RGB
        )


        # 显示截图

        h,w,c=img.shape

        qimg=QImage(
            img.data,
            w,
            h,
            w*c,
            QImage.Format_RGB888
        )


        pix=QPixmap.fromImage(
            qimg
        )


        self.image.setPixmap(
            pix.scaled(
                self.image.size(),
                Qt.KeepAspectRatio
            )
        )



        # OCR

        start=time.time()


        result=reader.readtext(
            img,
            detail=0
        )


        cost=time.time()-start


        text=" ".join(result)


        self.result.setText(
            f"识别数字:{text}\n耗时:{cost:.2f}s"
        )



if __name__=="__main__":

    app=QApplication(sys.argv)

    win=MainWindow()

    win.show()

    sys.exit(
        app.exec_()
    )