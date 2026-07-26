import sys
import os
import re
import numpy as np
from PIL import Image, ImageGrab
import easyocr

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QCheckBox, QTextEdit, QSystemTrayIcon, QMenu
)
from PyQt5.QtCore import QTimer, Qt, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QIcon

# 优化 CPU 线程数，防止多线程竞争
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

class SelectionWindow(QWidget):
    """屏幕区域选择框"""
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.begin = None
        self.end = None
        self.selected_rect = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.begin = event.pos()
            self.end = self.begin
            self.update()

    def mouseMoveEvent(self, event):
        if self.begin:
            self.end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.end = event.pos()
            x1 = min(self.begin.x(), self.end.x())
            y1 = min(self.begin.y(), self.end.y())
            w = abs(self.begin.x() - self.end.x())
            h = abs(self.begin.y() - self.end.y())
            if w > 10 and h > 10:
                self.selected_rect = (x1, y1, w, h)
            self.close()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))
        if self.begin and self.end:
            r = QRect(self.begin, self.end).normalized()
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
            painter.drawRect(r)
            painter.fillRect(r, QColor(255, 255, 255, 30))

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕数字监控告警器 (EasyOCR 版)")
        self.setGeometry(300, 300, 450, 400)

        # 核心监控参数
        self.monitor_rect = None
        self.timer = QTimer()
        self.timer.timeout.connect(self.process_screen_ocr)

        # 初始化 EasyOCR Reader (单例加载，加速推理)
        print("正在加载 EasyOCR 引擎...")
        self.reader = easyocr.Reader(['en'], gpu=False)
        print("EasyOCR 引擎加载完成！")

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 1. 区域选择控件
        area_layout = QHBoxLayout()
        self.btn_select = QPushButton("选择屏幕区域")
        self.btn_select.clicked.connect(self.start_selection)
        self.lbl_rect = QLabel("当前选中区域: 未选择")
        area_layout.addWidget(self.btn_select)
        area_layout.addWidget(self.lbl_rect)
        layout.addLayout(area_layout)

        # 2. 阈值与频率设置
        thresh_layout = QHBoxLayout()
        thresh_layout.addWidget(QLabel("触发告警阈值:"))
        self.input_threshold = QLineEdit("100.0")
        thresh_layout.addWidget(self.input_threshold)

        thresh_layout.addWidget(QLabel("检测间隔(秒):"))
        self.input_interval = QLineEdit("2")
        thresh_layout.addWidget(self.input_interval)
        layout.addLayout(thresh_layout)

        # 3. 告警控制按钮
        ctrl_layout = QHBoxLayout()
        self.btn_start = QPushButton("启动监控")
        self.btn_start.clicked.connect(self.toggle_monitoring)
        self.btn_start.setEnabled(False)
        ctrl_layout.addWidget(self.btn_start)
        layout.addLayout(ctrl_layout)

        # 4. 实时日志展示
        layout.addWidget(QLabel("运行日志:"))
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout.addWidget(self.txt_log)

    def log(self, message):
        self.txt_log.append(message)

    def start_selection(self):
        self.hide()
        self.selection_win = SelectionWindow()
        self.selection_win.showMaximized()
        self.selection_win.destroyed.connect(self.on_selection_finished)

    def on_selection_finished(self):
        self.show()
        rect = self.selection_win.selected_rect
        if rect:
            self.monitor_rect = rect
            self.lbl_rect.setText(f"选中区域: X={rect[0]}, Y={rect[1]}, W={rect[2]}, H={rect[3]}")
            self.btn_start.setEnabled(True)
            self.log(f"已设置监控区域: {rect}")
        else:
            self.log("选择取消或区域过小！")

    def toggle_monitoring(self):
        if self.timer.isActive():
            self.timer.stop()
            self.btn_start.setText("启动监控")
            self.btn_select.setEnabled(True)
            self.log("监控已停止。")
        else:
            try:
                interval_sec = float(self.input_interval.text())
                self.timer.start(int(interval_sec * 1000))
                self.btn_start.setText("停止监控")
                self.btn_select.setEnabled(False)
                self.log("监控运行中...")
            except ValueError:
                self.log("错误：请输入有效的间隔秒数！")

    def process_screen_ocr(self):
        if not self.monitor_rect:
            return

        x, y, w, h = self.monitor_rect
        # 截图区域 bbox: (left, upper, right, lower)
        bbox = (x, y, x + w, y + h)
        img_pil = ImageGrab.grab(bbox=bbox)

        # 转为 numpy 数组传给 EasyOCR
        img_np = np.array(img_pil)

        try:
            # 限制 allowlist 仅识别数字和小数点
            results = self.reader.readtext(img_np, allowlist='0123456789.')
            recognized_text = "".join([res[1] for res in results]).strip()

            if recognized_text:
                self.log(f"识别结果: '{recognized_text}'")
                # 提取数值对比阈值
                numbers = re.findall(r"\d+\.?\d*", recognized_text)
                if numbers:
                    val = float(numbers[0])
                    threshold = float(self.input_threshold.text())
                    if val >= threshold:
                        self.log(f"⚠️ 警告: 当前数值 {val} 超出阈值 {threshold}！")
            else:
                self.log("未检测到有效数字。")
        except Exception as e:
            self.log(f"OCR 识别异常: {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())