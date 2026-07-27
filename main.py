import sys
import time
import cv2
import mss
import numpy as np

from PyQt5.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout
)

from PyQt5.QtGui import (
    QPixmap,
    QImage,
    QPainter,
    QPen
)

from PyQt5.QtCore import Qt

from paddleocr import PaddleOCR


# ===============================
# OCR初始化
# ===============================

print("正在加载OCR模型...")

ocr = PaddleOCR(
    use_angle_cls=False,
    lang="en"
)

print("OCR加载完成")


# ===============================
# 屏幕区域框选窗口
# ===============================

class SelectWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.start = None
        self.end = None

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )

        self.setWindowOpacity(0.25)

        self.setStyleSheet(
            "background-color:black;"
        )

        screen = QApplication.primaryScreen()

        size = screen.size()

        self.setGeometry(
            0,
            0,
            size.width(),
            size.height()
        )


    def mousePressEvent(self, event):

        if event.button() == Qt.LeftButton:

            self.start = event.pos()
            self.end = self.start


    def mouseMoveEvent(self, event):

        if self.start:

            self.end = event.pos()

            self.update()


    def mouseReleaseEvent(self, event):

        if self.start:

            self.end = event.pos()

            self.close()


    def paintEvent(self, event):

        if self.start and self.end:

            painter = QPainter(self)

            pen = QPen(
                Qt.red,
                3
            )

            painter.setPen(pen)


            painter.drawRect(
                self.start.x(),
                self.start.y(),
                self.end.x() - self.start.x(),
                self.end.y() - self.start.y()
            )


    def get_area(self):

        x1 = self.start.x()
        y1 = self.start.y()

        x2 = self.end.x()
        y2 = self.end.y()


        return (

            min(x1, x2),
            min(y1, y2),
            abs(x2-x1),
            abs(y2-y1)

        )



# ===============================
# 主窗口
# ===============================

class MainWindow(QWidget):

    def __init__(self):

        super().__init__()


        self.setWindowTitle(
            "数字报警 V1.0"
        )

        self.resize(
            600,
            500
        )


        self.area = None


        self.label_area = QLabel(
            "识别区域: 未选择"
        )


        self.label_result = QLabel(
            "识别数字:"
        )


        self.preview = QLabel()

        self.preview.setFixedSize(
            400,
            200
        )


        self.btn_select = QPushButton(
            "框选数字区域"
        )


        self.btn_test = QPushButton(
            "点击测试识别"
        )


        self.btn_select.clicked.connect(
            self.select_area
        )


        self.btn_test.clicked.connect(
            self.test_ocr
        )


        layout = QVBoxLayout()


        layout.addWidget(
            self.btn_select
        )


        layout.addWidget(
            self.label_area
        )


        layout.addWidget(
            self.btn_test
        )


        layout.addWidget(
            self.preview
        )


        layout.addWidget(
            self.label_result
        )


        self.setLayout(layout)



    # ===========================
    # 框选区域
    # ===========================

    def select_area(self):

        self.selector = SelectWindow()

        self.selector.show()

        self.selector.closeEvent = self.area_close



    def area_close(self, event):

        self.area = self.selector.get_area()


        self.label_area.setText(
            f"识别区域:{self.area}"
        )



    # ===========================
    # OCR测试
    # ===========================

    def test_ocr(self):

        if not self.area:

            self.label_result.setText(
                "请先框选区域"
            )

            return


        x, y, w, h = self.area


        with mss.mss() as sct:

            screenshot = sct.grab({

                "left": x,

                "top": y,

                "width": w,

                "height": h

            })


        img = np.array(
            screenshot
        )


        img = cv2.cvtColor(
            img,
            cv2.COLOR_BGRA2BGR
        )


        # 显示截图

        rgb = cv2.cvtColor(
            img,
            cv2.COLOR_BGR2RGB
        )


        height, width, channel = rgb.shape


        qimg = QImage(

            rgb.data,

            width,

            height,

            width * channel,

            QImage.Format_RGB888

        )


        self.preview.setPixmap(

            QPixmap.fromImage(qimg)
            .scaled(
                350,
                150,
                Qt.KeepAspectRatio
            )

        )


        # OCR识别

        start = time.time()


        result = ocr.ocr(
            img,
            cls=False
        )


        text = ""


        if result:

            for line in result:

                if line:

                    for item in line:

                        text += item[1][0] + " "



        cost = time.time() - start


        self.label_result.setText(

            f"识别数字:{text}\n"
            f"耗时:{cost:.2f}秒"

        )



# ===============================
# 程序入口
# ===============================

if __name__ == "__main__":


    app = QApplication(sys.argv)


    window = MainWindow()


    window.show()


    sys.exit(
        app.exec_()
    )