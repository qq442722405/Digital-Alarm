import sys
import os
import multiprocessing

# ---------- [0. 核心防崩溃配置：拦截 C++ 底层冲突与日志] ----------
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["GLOG_minloglevel"] = "3"
os.environ["OMP_NUM_THREADS"] = "1"

# ---------- [1. stdout/stderr 守护：解决 --noconsole 模式下写日志崩溃] ----------
class NullStream:
    def write(self, text): pass
    def flush(self): pass
    def isatty(self): return False
    def writelines(self, lines): pass

if sys.stdout is None or not hasattr(sys.stdout, 'write'):
    sys.stdout = NullStream()
if sys.stderr is None or not hasattr(sys.stderr, 'write'):
    sys.stderr = NullStream()

import json
import traceback
import logging
import numpy as np
from datetime import datetime
import ctypes

# ---------- [2. 静态资源与 PaddleOCR 字典路径自动寻址 (关键修复)] ----------
def get_resource_path(relative_path):
    """获取打包后 _MEIPASS 临时解压目录或当前目录的绝对路径"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

def get_ppocr_dict_path():
    """自动定位 PaddleOCR 识别所需的字典文件，防止打包后找不到字典文件崩溃"""
    if hasattr(sys, '_MEIPASS'):
        possible_paths = [
            os.path.join(sys._MEIPASS, "paddleocr", "ppocr", "utils", "en_dict.txt"),
            os.path.join(sys._MEIPASS, "ppocr", "utils", "en_dict.txt"),
        ]
        for p in possible_paths:
            if os.path.exists(p):
                return p
    try:
        import paddleocr
        base_dir = os.path.dirname(paddleocr.__file__)
        dict_p = os.path.join(base_dir, "ppocr", "utils", "en_dict.txt")
        if os.path.exists(dict_p):
            return dict_p
    except Exception:
        pass
    return None

def get_icon_path():
    for name in ["1.ICO", "1.ico"]:
        path = get_resource_path(name)
        if os.path.exists(path):
            return path
    return None

# ---------- [3. 崩溃捕获与弹窗] ----------
def global_exception_handler(exc_type, exc_value, exc_traceback):
    err_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    try:
        with open("crash_log.txt", "w", encoding="utf-8") as f:
            f.write(f"崩溃时间: {datetime.now()}\n\n{err_msg}")
    except Exception:
        pass
    
    try:
        ctypes.windll.user32.MessageBoxW(
            0, 
            f"程序遇到错误:\n\n{exc_value}\n\n详细崩溃日志已保存至 crash_log.txt", 
            "数字报警 - 运行时错误", 
            0x10
        )
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

sys.excepthook = global_exception_handler

# ---------- [4. 高 DPI 兼容性] ----------
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QLineEdit, QLabel, QTextEdit, QGroupBox, QMessageBox,
    QSlider, QDoubleSpinBox, QFileDialog
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QIcon, QImage, QPixmap, QRegion
from PIL import Image, ImageEnhance, ImageGrab
import winsound

# ---------- [5. 屏幕框选器] ----------
class SnippingWidget(QWidget):
    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setCursor(Qt.CrossCursor)
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        self.bg_pixmap = None
        self.tip_text = ""

    def start_snipping(self, tip_text=""):
        self.tip_text = tip_text
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        try:
            try:
                img_pil = ImageGrab.grab(all_screens=True).convert("RGB")
            except Exception:
                img_pil = ImageGrab.grab().convert("RGB")
            data = img_pil.tobytes("raw", "RGB")
            qimg = QImage(data, img_pil.width, img_pil.height, 3 * img_pil.width, QImage.Format_RGB888)
            self.bg_pixmap = QPixmap.fromImage(qimg)
            self.setGeometry(0, 0, img_pil.width, img_pil.height)
        except Exception as e:
            QMessageBox.critical(None, "截图失败", f"无法获取屏幕截图: {e}")
            return
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.bg_pixmap:
            painter.drawPixmap(0, 0, self.bg_pixmap)

        overlay_color = QColor(0, 0, 0, 120)
        if self.start_pos and self.end_pos:
            rect = QRect(self.start_pos, self.end_pos).normalized()
            if rect.width() > 0 and rect.height() > 0:
                full_region = QRegion(self.rect())
                selected_region = QRegion(rect)
                dim_region = full_region.subtracted(selected_region)
                painter.setClipRegion(dim_region)
                painter.fillRect(self.rect(), overlay_color)
                painter.setClipping(False)
                painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
                painter.drawRect(rect)
            else:
                painter.fillRect(self.rect(), overlay_color)
        else:
            painter.fillRect(self.rect(), overlay_color)

        painter.setPen(QPen(Qt.white))
        font = painter.font()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(50, 50, f"{self.tip_text} (按 ESC 退出框选)")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            self.is_selecting = True
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_pos = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.end_pos = event.pos()
            rect = QRect(self.start_pos, self.end_pos).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self.region_selected.emit(rect)
                self.hide()
            else:
                self.start_pos = None
                self.end_pos = None
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()

# ---------- [6. 后台 OCR 识别线程] ----------
class OCRWorker(QThread):
    result_signal = pyqtSignal(list)

    def __init__(self, regions, ocr_engine, sharpness=0, scale=1.0, keep_digits_only=True):
        super().__init__()
        self.regions = regions
        self.ocr_engine = ocr_engine
        self.sharpness = sharpness
        self.scale = scale
        self.keep_digits_only = keep_digits_only
        self.running = False

    def preprocess(self, img_pil):
        if self.sharpness > 0:
            enhancer = ImageEnhance.Sharpness(img_pil)
            img_pil = enhancer.enhance(1.0 + self.sharpness / 100.0 * 2.0)
        if self.scale != 1.0:
            w, h = img_pil.size
            img_pil = img_pil.resize((int(w * self.scale), int(h * self.scale)), Image.LANCZOS)
        return img_pil

    def run(self):
        self.running = True
        while self.running:
            results = []
            for rect in self.regions:
                if not self.running:
                    break
                if rect is None or rect.width() < 5 or rect.height() < 5:
                    results.append("")
                    continue

                try:
                    bbox = (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
                    img_pil = ImageGrab.grab(bbox=bbox)
                    img_pil = self.preprocess(img_pil)
                    img_np = np.array(img_pil)
                    
                    ocr_res = self.ocr_engine.ocr(img_np, cls=False)
                    if ocr_res and ocr_res[0]:
                        text = " ".join([line[1][0] for line in ocr_res[0]])
                    else:
                        text = ""
                except Exception:
                    text = ""

                if self.keep_digits_only:
                    allowed = set("0123456789.-")
                    text = "".join([c for c in text if c in allowed])
                results.append(text.strip())

            if self.running:
                self.result_signal.emit(results)
                self.msleep(250)

    def stop(self):
        self.running = False

# ---------- [7. 主界面窗口] ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数字屏幕监控报警工具")
        self.setGeometry(100, 100, 1050, 800)

        ico_path = get_icon_path()
        if ico_path:
            icon = QIcon(ico_path)
            self.setWindowIcon(icon)
            QApplication.setWindowIcon(icon)

        self.ocr_engine = None
        self.config_file = "config.json"
        self.regions = [None] * 10
        self.alarm_value = ""
        self.comp_op = "="
        self.debounce_counts = [0] * 10
        self.debounce_threshold = 3
        self.alarm_active = False
        self.total_alarm_count = 0
        self.ocr_thread = None
        self.current_set_row = -1

        self.snipping_widget = SnippingWidget()
        self.snipping_widget.region_selected.connect(self.on_region_selected)

        self.init_ui()
        self.load_config()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 顶栏
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始监控")
        self.btn_stop = QPushButton("■ 停止监控")
        self.btn_stop.setEnabled(False)
        self.btn_save = QPushButton("💾 保存配置")
        self.btn_load = QPushButton("📂 加载配置")
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_load)
        main_layout.addLayout(btn_layout)

        # 路径与模型设置
        model_group = QGroupBox("OCR 模型路径")
        model_layout = QHBoxLayout(model_group)
        self.check_custom_model = QCheckBox("使用自定义本地识别模型目录")
        self.edit_rec_model_path = QLineEdit()
        self.btn_select_model = QPushButton("选择文件夹...")
        self.btn_select_model.setEnabled(False)
        self.check_custom_model.toggled.connect(lambda c: self.btn_select_model.setEnabled(c))
        self.btn_select_model.clicked.connect(self.select_local_model)
        model_layout.addWidget(self.check_custom_model)
        model_layout.addWidget(self.edit_rec_model_path)
        model_layout.addWidget(self.btn_select_model)
        main_layout.addWidget(model_group)

        # 报警设置
        alarm_group = QGroupBox("报警条件设置")
        alarm_layout = QHBoxLayout(alarm_group)
        alarm_layout.addWidget(QLabel("报警数值:"))
        self.edit_alarm_value = QLineEdit()
        self.edit_alarm_value.setMaximumWidth(120)
        alarm_layout.addWidget(self.edit_alarm_value)
        alarm_layout.addWidget(QLabel("触发条件:"))
        self.combo_comp_op = QComboBox()
        self.combo_comp_op.addItems(["=", ">", "<", "≥", "≤"])
        alarm_layout.addWidget(self.combo_comp_op)
        alarm_layout.addStretch()
        main_layout.addWidget(alarm_group)

        # 表格
        self.table = QTableWidget(10, 5)
        self.table.setHorizontalHeaderLabels(["行号", "操作", "区域坐标 X, Y, W, H", "实时识别值", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        for i in range(10):
            self.table.setItem(i, 0, QTableWidgetItem(f"第 {i+1} 行"))
            btn = QPushButton("框选")
            btn.clicked.connect(lambda checked, row=i: self.set_single_region(row))
            self.table.setCellWidget(i, 1, btn)
            self.table.setItem(i, 2, QTableWidgetItem("未框选"))
            self.table.setItem(i, 3, QTableWidgetItem(""))
            self.table.setItem(i, 4, QTableWidgetItem("待设置"))
        main_layout.addWidget(self.table)

        # 声音设置
        sound_group = QGroupBox("报警声音")
        sound_layout = QHBoxLayout(sound_group)
        self.combo_system_sound = QComboBox()
        self.combo_system_sound.addItems(["SystemExclamation", "SystemAsterisk", "SystemHand", "SystemQuestion"])
        sound_layout.addWidget(self.combo_system_sound)
        self.check_loop = QCheckBox("循环播放")
        self.check_mute = QCheckBox("静音")
        sound_layout.addWidget(self.check_loop)
        sound_layout.addWidget(self.check_mute)
        sound_layout.addStretch()
        main_layout.addWidget(sound_group)

        # 预处理
        preproc_group = QGroupBox("图像预处理")
        preproc_layout = QHBoxLayout(preproc_group)
        preproc_layout.addWidget(QLabel("锐化强度:"))
        self.slider_sharpness = QSlider(Qt.Horizontal)
        self.slider_sharpness.setRange(0, 100)
        preproc_layout.addWidget(self.slider_sharpness)
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setValue(1.0)
        preproc_layout.addWidget(QLabel("放大倍数:"))
        preproc_layout.addWidget(self.spin_scale)
        self.check_digits_only = QCheckBox("仅保留数字")
        self.check_digits_only.setChecked(True)
        preproc_layout.addWidget(self.check_digits_only)
        main_layout.addWidget(preproc_group)

        # 日志
        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)

        self.btn_start.clicked.connect(self.start_monitor)
        self.btn_stop.clicked.connect(self.stop_monitor)
        self.btn_save.clicked.connect(self.save_config)
        self.btn_load.clicked.connect(self.load_config)

    def select_local_model(self):
        dir_path = QFileDialog.getExistingDirectory(self, "选择模型文件夹")
        if dir_path:
            self.edit_rec_model_path.setText(dir_path)

    def set_single_region(self, row):
        self.current_set_row = row
        self.snipping_widget.start_snipping(f"请框选第 {row+1} 行区域")

    def on_region_selected(self, rect):
        if 0 <= self.current_set_row < 10:
            self.regions[self.current_set_row] = rect
            self.table.setItem(self.current_set_row, 2, QTableWidgetItem(f"{rect.x()}, {rect.y()}, {rect.width()}, {rect.height()}"))
            self.table.setItem(self.current_set_row, 4, QTableWidgetItem("待监控"))

    # ---------- [8. 安全初始化 PaddleOCR (兼容打包环境)] ----------
    def start_monitor(self):
        if all(r is None for r in self.regions):
            QMessageBox.warning(self, "提示", "请至少指定 1 个识别区域！")
            return

        if self.ocr_engine is None:
            self.log("正在初始化 PaddleOCR 引擎...")
            QApplication.processEvents()

            try:
                from paddleocr import PaddleOCR
            except Exception as e:
                QMessageBox.critical(self, "环境错误", f"导入 PaddleOCR 失败: {e}")
                return

            try:
                dict_path = get_ppocr_dict_path()
                ocr_kwargs = {
                    "lang": 'en',
                    "show_log": False,
                    "use_gpu": False,
                    "use_angle_cls": False
                }
                
                # 自动传入打包后的字典路径
                if dict_path and os.path.exists(dict_path):
                    ocr_kwargs["rec_char_dict_path"] = dict_path

                custom_dir = self.edit_rec_model_path.text().strip()
                if self.check_custom_model.isChecked() and custom_dir and os.path.exists(custom_dir):
                    ocr_kwargs["rec_model_dir"] = custom_dir

                self.ocr_engine = PaddleOCR(**ocr_kwargs)
                self.log("PaddleOCR 引擎加载成功！")
            except Exception as e:
                QMessageBox.critical(self, "初始化崩溃", f"PaddleOCR 初始化失败:\n{e}")
                return

        self.alarm_value = self.edit_alarm_value.text().strip()
        self.comp_op = self.combo_comp_op.currentText()

        if self.ocr_thread and self.ocr_thread.isRunning():
            self.ocr_thread.stop()
            self.ocr_thread.wait()

        self.ocr_thread = OCRWorker(
            self.regions, self.ocr_engine,
            sharpness=self.slider_sharpness.value(),
            scale=self.spin_scale.value(),
            keep_digits_only=self.check_digits_only.isChecked()
        )
        self.ocr_thread.result_signal.connect(self.process_results)
        self.ocr_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log("▶ 屏幕监控已启动。")

    def stop_monitor(self):
        if self.ocr_thread and self.ocr_thread.isRunning():
            self.ocr_thread.stop()
            self.ocr_thread.wait()

        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.log("■ 监控已停止。")

    def process_results(self, results):
        for i, text in enumerate(results):
            if i >= 10: break
            self.table.item(i, 3).setText(text)
            if self.regions[i] is not None:
                self.table.item(i, 4).setText("监控中" if text else "未识别")

    def log(self, message):
        self.log_text.append(message)

    def save_config(self):
        config = {"alarm_value": self.edit_alarm_value.text()}
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f)
        QMessageBox.information(self, "成功", "配置已保存")

    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
                self.edit_alarm_value.setText(config.get("alarm_value", ""))
            except Exception: pass

    def closeEvent(self, event):
        self.stop_monitor()
        event.accept()

# ---------- [9. 程序统一入口 (必须包含 freeze_support)] ----------
if __name__ == "__main__":
    multiprocessing.freeze_support()  # 打包 EXE 必加项
    
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
