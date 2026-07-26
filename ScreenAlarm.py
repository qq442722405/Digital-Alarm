import os
import sys

# =====================================================================
# 1. 修复 --noconsole 模式下 PaddleOCR print 打印日志导致的闪退崩溃
# =====================================================================
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

# =====================================================================
# 2. 获取打包后的资源（如图标 1.ico）绝对路径
# =====================================================================
def resource_path(relative_path):
    """获取打包后临时目录中的资源绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


import re
import time
import winsound
import numpy as np
from PIL import ImageGrab

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QComboBox, QTextEdit, QSpinBox,
    QMessageBox, QGroupBox, QGridLayout
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QRect, QPoint
from PyQt5.QtGui import QIcon, QPainter, QPen, QColor, QFont


class SnippingWidget(QWidget):
    """屏幕区域框选遮罩控件"""
    region_selected = pyqtSignal(tuple)  # 发送框选坐标 (x, y, w, h)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setWindowState(Qt.WindowFullScreen)
        self.setWindowOpacity(0.3)
        self.setCursor(Qt.CrossCursor)

        self.start_point = QPoint()
        self.end_point = QPoint()
        self.is_selecting = False

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.end_point = event.pos()
            self.is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.end_point = event.pos()

            x1 = min(self.start_point.x(), self.end_point.x())
            y1 = min(self.start_point.y(), self.end_point.y())
            w = abs(self.start_point.x() - self.end_point.x())
            h = abs(self.start_point.y() - self.end_point.y())

            self.hide()
            if w > 5 and h > 5:
                self.region_selected.emit((x1, y1, w, h))

    def paintEvent(self, event):
        if self.is_selecting:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
            painter.setBrush(QColor(255, 255, 255, 50))
            rect = QRect(self.start_point, self.end_point).normalized()
            painter.drawRect(rect)


class MonitorThread(QThread):
    """后台屏幕监控与 PaddleOCR 识别线程"""
    update_signal = pyqtSignal(str, float)  # raw_text, parsed_number
    log_signal = pyqtSignal(str)           # log_message
    alarm_signal = pyqtSignal(str)         # alarm_reason
    error_signal = pyqtSignal(str)         # error_message

    def __init__(self, region, condition, threshold, interval):
        super().__init__()
        self.region = region          # (x, y, w, h)
        self.condition = condition    # ">", "<", "==", "!="
        self.threshold = threshold    # float
        self.interval = interval      # int (seconds)
        self.running = False
        self.ocr = None

    def run(self):
        self.running = True
        self.log_signal.emit("正在初始化 PaddleOCR 引擎...")

        # 在子线程中初始化 OCR，避免卡死界面
        try:
            from paddleocr import PaddleOCR
            self.ocr = PaddleOCR(use_angle_cls=False, lang='en', show_log=False)
            self.log_signal.emit("PaddleOCR 初始化成功，开始监听...")
        except Exception as e:
            self.error_signal.emit(f"无法导入或初始化 PaddleOCR 库:\n{e}")
            self.running = False
            return

        x, y, w, h = self.region
        bbox = (x, y, x + w, y + h)

        while self.running:
            try:
                # 截取指定区域屏幕
                img = ImageGrab.grab(bbox=bbox)
                img_np = np.array(img)

                # 执行 OCR 文本识别
                result = self.ocr.ocr(img_np, cls=False)

                detected_text = ""
                if result and result[0]:
                    for line in result[0]:
                        detected_text += line[1][0] + " "

                detected_text = detected_text.strip()

                # 正则提取数字（支持整数、浮点数与负数）
                numbers = re.findall(r"[-+]?\d*\.\d+|\d+", detected_text)

                if numbers:
                    val = float(numbers[0])
                    self.update_signal.emit(detected_text, val)

                    # 判断报警阈值
                    triggered = False
                    if self.condition == ">" and val > self.threshold:
                        triggered = True
                    elif self.condition == "<" and val < self.threshold:
                        triggered = True
                    elif self.condition == "==" and abs(val - self.threshold) < 1e-5:
                        triggered = True
                    elif self.condition == "!=" and abs(val - self.threshold) >= 1e-5:
                        triggered = True

                    if triggered:
                        msg = f"检测数值 [{val}] 触发条件 [{self.condition} {self.threshold}]！"
                        self.alarm_signal.emit(msg)
                else:
                    self.update_signal.emit(detected_text if detected_text else "未识别到文本", float('nan'))

            except Exception as e:
                self.log_signal.emit(f"识别过程异常: {e}")

            # 响应停止事件的平滑休眠
            for _ in range(self.interval * 10):
                if not self.running:
                    break
                time.sleep(0.1)

    def stop(self):
        self.running = False
        self.wait()


class ScreenAlarmApp(QMainWindow):
    """主程序界面"""
    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕数字监控报警器 v1.0")
        self.setFixedSize(520, 580)

        # 加载图标资源
        icon_path = resource_path("1.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.region = None
        self.monitor_thread = None
        self.snipper = SnippingWidget()
        self.snipper.region_selected.connect(self.on_region_selected)

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # 1. 区域设置
        group_region = QGroupBox("1. 监控区域")
        layout_region = QHBoxLayout()
        self.btn_select_region = QPushButton("框选屏幕区域")
        self.btn_select_region.clicked.connect(self.start_snipping)
        self.lbl_region_info = QLabel("未选择区域")
        self.lbl_region_info.setStyleSheet("color: gray;")
        layout_region.addWidget(self.btn_select_region)
        layout_region.addWidget(self.lbl_region_info)
        group_region.setLayout(layout_region)
        main_layout.addWidget(group_region)

        # 2. 规则配置
        group_rule = QGroupBox("2. 报警规则")
        layout_rule = QGridLayout()

        layout_rule.addWidget(QLabel("触发条件:"), 0, 0)
        self.combo_condition = QComboBox()
        self.combo_condition.addItems([">", "<", "==", "!="])
        layout_rule.addWidget(self.combo_condition, 0, 1)

        layout_rule.addWidget(QLabel("阈值数字:"), 0, 2)
        self.input_threshold = QLineEdit("100")
        layout_rule.addWidget(self.input_threshold, 0, 3)

        layout_rule.addWidget(QLabel("检测间隔(秒):"), 1, 0)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 3600)
        self.spin_interval.setValue(2)
        layout_rule.addWidget(self.spin_interval, 1, 1)

        self.btn_test_sound = QPushButton("测试蜂鸣音")
        self.btn_test_sound.clicked.connect(self.play_alarm_sound)
        layout_rule.addWidget(self.btn_test_sound, 1, 2, 1, 2)

        group_rule.setLayout(layout_rule)
        main_layout.addWidget(group_rule)

        # 3. 控制按钮
        layout_control = QHBoxLayout()
        self.btn_toggle = QPushButton("开始监控")
        self.btn_toggle.setFixedHeight(40)
        self.btn_toggle.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self.btn_toggle.setStyleSheet("background-color: #4CAF50; color: white;")
        self.btn_toggle.clicked.connect(self.toggle_monitoring)
        layout_control.addWidget(self.btn_toggle)
        main_layout.addLayout(layout_control)

        # 4. 实时展示
        group_display = QGroupBox("3. 实时状态")
        layout_display = QGridLayout()

        layout_display.addWidget(QLabel("OCR 文本:"), 0, 0)
        self.lbl_raw_text = QLabel("-")
        self.lbl_raw_text.setStyleSheet("font-weight: bold;")
        layout_display.addWidget(self.lbl_raw_text, 0, 1)

        layout_display.addWidget(QLabel("识别数值:"), 1, 0)
        self.lbl_parsed_val = QLabel("-")
        self.lbl_parsed_val.setStyleSheet("font-size: 16px; font-weight: bold; color: #2196F3;")
        layout_display.addWidget(self.lbl_parsed_val, 1, 1)

        group_display.setLayout(layout_display)
        main_layout.addWidget(group_display)

        # 5. 日志区
        group_log = QGroupBox("运行日志")
        layout_log = QVBoxLayout()
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        layout_log.addWidget(self.txt_log)
        group_log.setLayout(layout_log)
        main_layout.addWidget(group_log)

    def start_snipping(self):
        self.hide()
        time.sleep(0.2)
        self.snipper.show()

    def on_region_selected(self, region):
        self.show()
        self.region = region
        x, y, w, h = region
        self.lbl_region_info.setText(f"X:{x}, Y:{y} | 宽:{w}, 高:{h}")
        self.lbl_region_info.setStyleSheet("color: green; font-weight: bold;")
        self.append_log(f"已设置监控区域: {self.region}")

    def toggle_monitoring(self):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
            self.btn_toggle.setText("开始监控")
            self.btn_toggle.setStyleSheet("background-color: #4CAF50; color: white;")
            self.append_log("监控已停止。")
            self.btn_select_region.setEnabled(True)
        else:
            if not self.region:
                QMessageBox.warning(self, "警告", "请先框选屏幕监控区域！")
                return

            try:
                threshold = float(self.input_threshold.text().strip())
            except ValueError:
                QMessageBox.warning(self, "参数错误", "请输入有效的数字阈值！")
                return

            condition = self.combo_condition.currentText()
            interval = self.spin_interval.value()

            self.monitor_thread = MonitorThread(self.region, condition, threshold, interval)
            self.monitor_thread.update_signal.connect(self.on_update_status)
            self.monitor_thread.log_signal.connect(self.append_log)
            self.monitor_thread.alarm_signal.connect(self.trigger_alarm)
            self.monitor_thread.error_signal.connect(self.on_thread_error)

            self.monitor_thread.start()
            self.btn_toggle.setText("停止监控")
            self.btn_toggle.setStyleSheet("background-color: #f44336; color: white;")
            self.btn_select_region.setEnabled(False)

    def on_update_status(self, raw_text, val):
        self.lbl_raw_text.setText(raw_text)
        if np.isnan(val):
            self.lbl_parsed_val.setText("未包含数字")
        else:
            self.lbl_parsed_val.setText(str(val))

    def trigger_alarm(self, reason):
        self.append_log(f"🚨【报警】{reason}")
        self.play_alarm_sound()

    def play_alarm_sound(self):
        try:
            # 播放 Windows 蜂鸣音 (频率 1500Hz, 持续 600ms)
            winsound.Beep(1500, 600)
        except Exception:
            QApplication.beep()

    def on_thread_error(self, err_msg):
        QMessageBox.critical(self, "环境或运行错误", err_msg)
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.toggle_monitoring()

    def append_log(self, text):
        current_time = time.strftime("%H:%M:%S")
        self.txt_log.append(f"[{current_time}] {text}")

    def closeEvent(self, event):
        if self.monitor_thread and self.monitor_thread.isRunning():
            self.monitor_thread.stop()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    font = QFont("Microsoft YaHei", 9)
    app.setFont(font)

    window = ScreenAlarmApp()
    window.show()
    sys.exit(app.exec_())