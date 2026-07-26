import sys
import os
import re
import numpy as np

from PIL import ImageGrab

import easyocr


from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTextEdit
)

from PyQt5.QtCore import (
    QTimer,
    Qt,
    QRect
)

from PyQt5.QtGui import (
    QPainter,
    QPen,
    QColor
)



os.environ["OMP_NUM_THREADS"]="1"
os.environ["MKL_NUM_THREADS"]="1"



class SelectWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )

        self.setAttribute(
            Qt.WA_TranslucentBackground
        )

        self.start=None
        self.end=None
        self.rect=None



    def mousePressEvent(self,e):

        if e.button()==Qt.LeftButton:

            self.start=e.pos()
            self.end=e.pos()



    def mouseMoveEvent(self,e):

        if self.start:

            self.end=e.pos()
            self.update()



    def mouseReleaseEvent(self,e):

        if self.start:

            x=min(self.start.x(),self.end.x())
            y=min(self.start.y(),self.end.y())

            w=abs(self.start.x()-self.end.x())
            h=abs(self.start.y()-self.end.y())


            if w>10 and h>10:

                self.rect=(x,y,w,h)


            self.close()



    def paintEvent(self,e):

        p=QPainter(self)

        p.fillRect(
            self.rect(),
            QColor(0,0,0,80)
        )


        if self.start and self.end:

            r=QRect(
                self.start,
                self.end
            ).normalized()


            p.setPen(
                QPen(
                    QColor(255,0,0),
                    2
                )
            )

            p.drawRect(r)




class MainWindow(QMainWindow):


    def __init__(self):

        super().__init__()


        self.setWindowTitle(
            "数字报警"
        )


        self.resize(
            500,
            400
        )


        self.area=None


        self.timer=QTimer()

        self.timer.timeout.connect(
            self.detect
        )


        self.reader=easyocr.Reader(
            ['en'],
            gpu=False
        )


        self.init_ui()



    def init_ui(self):

        w=QWidget()

        self.setCentralWidget(w)


        layout=QVBoxLayout(w)



        row=QHBoxLayout()


        self.btn=QPushButton(
            "选择区域"
        )

        self.btn.clicked.connect(
            self.select
        )


        self.label=QLabel(
            "未选择"
        )


        row.addWidget(self.btn)

        row.addWidget(self.label)


        layout.addLayout(row)



        self.value=QLineEdit(
            "100"
        )


        layout.addWidget(
            QLabel("报警值")
        )


        layout.addWidget(
            self.value
        )



        self.startbtn=QPushButton(
            "开始监控"
        )


        self.startbtn.clicked.connect(
            self.start
        )


        layout.addWidget(
            self.startbtn
        )



        self.logbox=QTextEdit()

        self.logbox.setReadOnly(True)


        layout.addWidget(
            self.logbox
        )




    def log(self,t):

        self.logbox.append(t)



    def select(self):

        self.hide()

        self.sel=SelectWindow()

        self.sel.showMaximized()


        self.sel.destroyed.connect(
            self.finish_select
        )



    def finish_select(self):

        self.show()


        if self.sel.rect:

            self.area=self.sel.rect

            self.label.setText(
                str(self.area)
            )

            self.log(
                "区域设置完成"
            )



    def start(self):

        self.timer.start(2000)

        self.log(
            "开始监控"
        )



    def detect(self):

        if not self.area:

            return


        x,y,w,h=self.area


        img=ImageGrab.grab(
            (
                x,
                y,
                x+w,
                y+h
            )
        )


        result=self.reader.readtext(
            np.array(img),
            allowlist="0123456789."
        )


        text=""


        for r in result:

            text+=r[1]


        nums=re.findall(
            r"\d+\.?\d*",
            text
        )


        if nums:

            value=float(nums[0])


            self.log(
                f"识别:{value}"
            )


            if value>=float(
                self.value.text()
            ):

                self.log(
                    "报警!"
                )




if __name__=="__main__":


    app=QApplication(sys.argv)


    win=MainWindow()

    win.show()


    sys.exit(
        app.exec_()
    )