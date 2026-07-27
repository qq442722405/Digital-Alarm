import sys
import time

import numpy as np

import pyautogui

from PIL import Image

from paddleocr import PaddleOCR


from PyQt5.QtWidgets import *

from PyQt5.QtCore import *

from PyQt5.QtGui import *



# =====================
# OCR初始化
# =====================

ocr = PaddleOCR(
    lang="en"
)



# =====================
# 区域选择窗口
# =====================

class SelectWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )

        self.setWindowOpacity(0.3)

        self.start=None
        self.end=None
        self.rect=None


        self.showFullScreen()



    def mousePressEvent(self,e):

        self.start=e.pos()



    def mouseMoveEvent(self,e):

        self.end=e.pos()

        self.update()



    def mouseReleaseEvent(self,e):

        x1=self.start.x()
        y1=self.start.y()

        x2=self.end.x()
        y2=self.end.y()


        self.rect=(

            min(x1,x2),
            min(y1,y2),
            abs(x2-x1),
            abs(y2-y1)

        )


        self.close()



    def paintEvent(self,e):

        p=QPainter(self)

        p.fillRect(
            self.rect(),
            QColor(0,0,0,80)
        )


# =====================
# 主窗口
# =====================


class MainWindow(QMainWindow):


    def __init__(self):

        super().__init__()


        self.resize(
            500,
            400
        )


        self.area=None


        self.setWindowTitle(
            "数字识别测试 V1"
        )


        layout=QVBoxLayout()


        widget=QWidget()

        widget.setLayout(layout)

        self.setCentralWidget(widget)



        self.btn1=QPushButton(
            "选择识别区域"
        )

        self.btn1.clicked.connect(
            self.select
        )


        layout.addWidget(
            self.btn1
        )



        self.btn2=QPushButton(
            "开始识别"
        )

        self.btn2.clicked.connect(
            self.detect
        )


        layout.addWidget(
            self.btn2
        )



        self.result=QLabel(
            "识别结果:"
        )


        layout.addWidget(
            self.result
        )




        self.info=QLabel(
            ""
        )


        layout.addWidget(
            self.info
        )





    def select(self):

        self.hide()


        self.sel=SelectWindow()


        self.sel.destroyed.connect(
            self.get_area
        )



    def get_area(self):

        self.show()

        self.area=self.sel.rect


        self.info.setText(
            str(self.area)
        )





    def detect(self):

        if not self.area:

            return


        x,y,w,h=self.area


        img=pyautogui.screenshot(
            region=(
                x,
                y,
                w,
                h
            )
        )


        img=np.array(img)



        start=time.time()



        result=ocr.predict(
            img
        )


        cost=int(
            (time.time()-start)*1000
        )


        text=""


        try:

            for r in result:

                text+=str(
                    r
                )

        except:

            text="识别失败"



        self.result.setText(
            "识别结果:\n"+text
        )


        self.info.setText(
            f"耗时:{cost}ms"
        )





if __name__=="__main__":


    app=QApplication(sys.argv)


    w=MainWindow()

    w.show()


    sys.exit(
        app.exec_()
    )