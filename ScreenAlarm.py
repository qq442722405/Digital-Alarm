import sys
import json
import os
import numpy as np
from datetime import datetime
import ctypes

# ---------- 1. Windows 高 DPI 兼容性设置（必须在创建 QApplication 前执行，防止 DPI 导致的缩放闪退） ----------
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
    QSlider, QDoubleSpinBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QIcon
from paddleocr import PaddleOCR
from PIL import Image, ImageEnhance, ImageGrab
import winsound

# 获取 1.ICO 路径（兼容源码运行与打包后的临时目录）
def get_icon_path():
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    for name in ["1.ICO", "1.ico"]:
        path = os.path.join(base_path, name)
        if os.path.exists(path):
            return path
    return None


# ---------- 2. 全新设计的矢量半透明框选器（无截图，彻底避免闪退） ----------
class RegionSelector(QWidget):
    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        # 设置无边框、置顶、无任务栏图标
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        self.rect = QRect()
        self.tip_text = ""

    def show_selector(self, tip_text=""):
        self.tip_text = tip_text
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        self.rect = QRect()

        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        
        self.showFullScreen()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. 全屏填充半透明黑色暗色遮罩 (Alpha = 110)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))

        # 2. 绘制顶部指引文字
        painter.setPen(QPen(Qt.white))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(40, 50, f"{self.tip_text} （按 ESC 取消框选）")

        # 3. 拖拽框选实时绘制
        if self.rect.width() > 0 and self.rect.height() > 0:
            # 镂空选中区域（透出底层屏幕内容）
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.rect, Qt.transparent)
            
            # 恢复正常绘制模式
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # 绘制红框边框
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
            painter.drawRect(self.rect)

            # 绘制坐标提示小标签
            coord_info = f"X:{self.rect.x()} Y:{self.rect.y()} | W:{self.rect.width()} H:{self.rect.height()}"
            text_y = max(15, self.rect.y() - 25)
            
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 0, 0, 200))
            painter.drawRect(self.rect.x(), text_y, 230, 22)

            painter.setPen(QPen(Qt.white))
            font.setPointSize(10)
            painter.setFont(font)
            painter.drawText(self.rect.x() + 6, text_y + 16, coord_info)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.start_pos = event.pos()
            self.end_pos = event.pos()
            self.is_selecting = True
            self.rect = QRect(self.start_pos, self.end_pos).normalized()
            self.update()

    def mouseMoveEvent(self, event):
        if self.is_selecting:
            self.end_pos = event.pos()
            self.rect = QRect(self.start_pos, self.end_pos).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.is_selecting:
            self.is_selecting = False
            self.end_pos = event.pos()
            self.rect = QRect(self.start_pos, self.end_pos).normalized()

            if self.rect.width() > 5 and self.rect.height() > 5:
                self.region_selected.emit(self.rect)
                self.hide()
            else:
                self.rect = QRect()
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()


# ---------- 3. OCR 识别后台子线程 ----------
class OCRWorker(QThread):
    result_signal = pyqtSignal(list)

    def __init__(self, regions, ocr, sharpness=0, scale=1.0, keep_digits_only=True):
        super().__init__()
        self.regions = regions
        self.ocr = ocr
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

                    ocr_result = self.ocr.ocr(np.array(img_pil), cls=False)
                    if ocr_result and ocr_result[0]:
                        text = " ".join([line[1][0] for line in ocr_result[0]])
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


# ---------- 4. 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕监控报警工具")
        self.setGeometry(100, 100, 1050, 750)

        # 加载并应用 1.ICO 图标
        ico_path = get_icon_path()
        if ico_path:
            icon = QIcon(ico_path)
            self.setWindowIcon(icon)
            QApplication.setWindowIcon(icon)
            try:
                # 注册 AppUserModelID，保证 Windows 任务栏正确显示 1.ICO
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScreenMonitorAlarm.App.1.0")
            except Exception:
                pass

        self.ocr = None
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

        self.selector = RegionSelector()
        self.selector.region_selected.connect(self.on_region_selected)

        self.init_ui()
        self.load_config()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 1. 顶栏按钮
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

        # 2. 报警条件
        alarm_group = QGroupBox("报警条件设置")
        alarm_layout = QHBoxLayout(alarm_group)
        alarm_layout.addWidget(QLabel("报警数值:"))
        self.edit_alarm_value = QLineEdit()
        self.edit_alarm_value.setPlaceholderText("例如: 100")
        self.edit_alarm_value.setMaximumWidth(120)
        alarm_layout.addWidget(self.edit_alarm_value)
        alarm_layout.addWidget(QLabel("触发条件:"))
        self.combo_comp_op = QComboBox()
        self.combo_comp_op.addItems(["=", ">", "<", "≥", "≤"])
        alarm_layout.addWidget(self.combo_comp_op)
        alarm_layout.addStretch()
        main_layout.addWidget(alarm_group)

        # 3. 区域表格 (坐标支持手动编辑)
        self.table = QTableWidget(10, 5)
        self.table.setHorizontalHeaderLabels(["行号", "操作", "区域坐标 X, Y, W, H (可手动修改)", "实时识别值", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 230)
        self.table.setColumnWidth(3, 140)

        for i in range(10):
            self.table.setItem(i, 0, QTableWidgetItem(f"第 {i+1} 行"))
            self.table.item(i, 0).setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            
            btn = QPushButton("框选")
            btn.clicked.connect(lambda checked, row=i: self.set_single_region(row))
            self.table.setCellWidget(i, 1, btn)
            
            self.table.setItem(i, 2, QTableWidgetItem("未框选"))
            
            item_val = QTableWidgetItem("")
            item_val.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(i, 3, item_val)
            
            item_status = QTableWidgetItem("待设置")
            item_status.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(i, 4, item_status)

        self.table.itemChanged.connect(self.on_table_item_changed)
        main_layout.addWidget(self.table)

        # 4. 报警声音设置
        sound_group = QGroupBox("报警声音设置")
        sound_layout = QHBoxLayout(sound_group)
        sound_layout.addWidget(QLabel("系统声音:"))
        self.combo_system_sound = QComboBox()
        self.combo_system_sound.addItems(["SystemExclamation", "SystemAsterisk", "SystemHand", "SystemQuestion", "SystemDefault"])
        sound_layout.addWidget(self.combo_system_sound)

        self.btn_test_sound = QPushButton("试听")
        sound_layout.addWidget(self.btn_test_sound)

        sound_layout.addSpacing(20)
        self.check_loop = QCheckBox("循环播放")
        self.check_mute = QCheckBox("静音")
        sound_layout.addWidget(self.check_loop)
        sound_layout.addWidget(self.check_mute)
        sound_layout.addStretch()
        main_layout.addWidget(sound_group)

        # 5. 图像预处理
        preproc_group = QGroupBox("图像预处理")
        preproc_layout = QHBoxLayout(preproc_group)
        preproc_layout.addWidget(QLabel("锐化强度:"))
        self.slider_sharpness = QSlider(Qt.Horizontal)
        self.slider_sharpness.setRange(0, 100)
        self.slider_sharpness.setValue(0)
        preproc_layout.addWidget(self.slider_sharpness)
        self.label_sharpness_val = QLabel("0")
        preproc_layout.addWidget(self.label_sharpness_val)

        preproc_layout.addSpacing(20)
        preproc_layout.addWidget(QLabel("放大倍数:"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(1.0, 4.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(1.0)
        preproc_layout.addWidget(self.spin_scale)

        self.check_digits_only = QCheckBox("仅保留数字与小数点")
        self.check_digits_only.setChecked(True)
        preproc_layout.addSpacing(20)
        preproc_layout.addWidget(self.check_digits_only)
        preproc_layout.addStretch()
        main_layout.addWidget(preproc_group)

        # 6. 日志区域
        log_group = QGroupBox("报警日志")
        log_layout = QVBoxLayout(log_group)
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("触发总次数:"))
        self.label_alarm_count = QLabel("0")
        count_layout.addWidget(self.label_alarm_count)
        count_layout.addStretch()
        log_layout.addLayout(count_layout)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)

        # 事件绑定
        self.btn_start.clicked.connect(self.start_monitor)
        self.btn_stop.clicked.connect(self.stop_monitor)
        self.btn_save.clicked.connect(self.save_config)
        self.btn_load.clicked.connect(self.load_config)
        self.btn_test_sound.clicked.connect(self.test_sound)
        self.slider_sharpness.valueChanged.connect(lambda v: self.label_sharpness_val.setText(str(v)))

    def quit_app(self):
        self.stop_monitor()
        QApplication.quit()

    def closeEvent(self, event):
        self.quit_app()
        event.accept()

    def test_sound(self):
        alias = self.combo_system_sound.currentText()
        try:
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass

    def play_alarm_sound(self):
        if self.check_mute.isChecked():
            return
        flags = winsound.SND_ASYNC
        if self.check_loop.isChecked():
            flags |= winsound.SND_LOOP

        alias = self.combo_system_sound.currentText()
        winsound.PlaySound(alias, winsound.SND_ALIAS | flags)

    def stop_alarm_sound(self):
        winsound.PlaySound(None, winsound.SND_PURGE)

    # ---------- 5. 框选与坐标更新 ----------
    def set_single_region(self, row):
        self.current_set_row = row
        tip = f"请框选【第 {row+1} 行】识别区域"
        self.selector.show_selector(tip)

    def on_region_selected(self, rect):
        if 0 <= self.current_set_row < 10:
            self.regions[self.current_set_row] = rect
            coord_str = f"{rect.x()}, {rect.y()}, {rect.width()}, {rect.height()}"
            
            self.table.blockSignals(True)
            self.table.setItem(self.current_set_row, 2, QTableWidgetItem(coord_str))
            btn = self.table.cellWidget(self.current_set_row, 1)
            if btn:
                btn.setText("重框选")
            self.table.setItem(self.current_set_row, 4, QTableWidgetItem("待监控"))
            self.table.blockSignals(False)

    def on_table_item_changed(self, item):
        if item.column() == 2:
            row = item.row()
            text = item.text().strip()
            try:
                parts = [int(p.strip()) for p in text.replace("，", ",").split(",")]
                if len(parts) == 4 and parts[2] > 0 and parts[3] > 0:
                    self.regions[row] = QRect(parts[0], parts[1], parts[2], parts[3])
                    self.table.item(row, 4).setText("待监控")
                else:
                    self.regions[row] = None
            except Exception:
                self.regions[row] = None

    # ---------- 6. 监控流程 ----------
    def start_monitor(self):
        if all(r is None for r in self.regions):
            QMessageBox.warning(self, "提示", "请至少指定 1 个识别区域！")
            return

        if self.ocr is None:
            self.log("正在初始化 OCR 引擎，请稍候...")
            QApplication.processEvents()
            try:
                self.ocr = PaddleOCR(use_angle_cls=False, lang='ch', show_log=False)
                self.log("OCR 引擎初始化成功。")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法初始化 PaddleOCR: {e}")
                return

        self.alarm_value = self.edit_alarm_value.text().strip()
        self.comp_op = self.combo_comp_op.currentText()

        if self.ocr_thread and self.ocr_thread.isRunning():
            self.ocr_thread.stop()
            self.ocr_thread.wait()

        self.ocr_thread = OCRWorker(
            self.regions, self.ocr,
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
        self.stop_alarm_sound()
        self.alarm_active = False
        self.log("■ 监控已停止。")

    def process_results(self, results):
        alarm_triggered = False
        alarm_rows = []

        for i, text in enumerate(results):
            if i >= 10:
                break
            self.table.item(i, 3).setText(text)

            if not text or self.regions[i] is None:
                if self.regions[i] is not None:
                    self.table.item(i, 4).setText("监测中...")
                self.debounce_counts[i] = 0
                continue

            try:
                current_val = float(text)
            except ValueError:
                self.table.item(i, 4).setText("非有效数字")
                self.debounce_counts[i] = 0
                continue

            if not self.alarm_value:
                self.table.item(i, 4).setText("未设报警值")
                self.debounce_counts[i] = 0
                continue

            try:
                alarm_val = float(self.alarm_value)
            except ValueError:
                self.table.item(i, 4).setText("阈值无效")
                self.debounce_counts[i] = 0
                continue

            op = self.comp_op
            condition_met = False
            if op == "=":
                condition_met = abs(current_val - alarm_val) < 1e-6
            elif op == ">":
                condition_met = current_val > alarm_val
            elif op == "<":
                condition_met = current_val < alarm_val
            elif op == "≥":
                condition_met = current_val >= alarm_val
            elif op == "≤":
                condition_met = current_val <= alarm_val

            if condition_met:
                self.debounce_counts[i] += 1
                if self.debounce_counts[i] >= self.debounce_threshold:
                    self.table.item(i, 4).setText("⚠️ 报警触发！")
                    alarm_triggered = True
                    alarm_rows.append(i + 1)
                else:
                    self.table.item(i, 4).setText("疑似超限...")
            else:
                self.debounce_counts[i] = 0
                self.table.item(i, 4).setText("正常")

        if alarm_triggered:
            if not self.alarm_active:
                self.play_alarm_sound()
                self.alarm_active = True
                self.total_alarm_count += 1
                self.label_alarm_count.setText(str(self.total_alarm_count))
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log(f"[{now}] 🚨 触发报警！行号: {alarm_rows} | 条件: {self.comp_op} {self.alarm_value}")
        else:
            if self.alarm_active:
                self.stop_alarm_sound()
                self.alarm_active = False

    def log(self, message):
        self.log_text.append(message)

    # ---------- 7. 配置文件保存与读取 ----------
    def save_config(self):
        config = {
            "regions": [],
            "alarm_value": self.edit_alarm_value.text(),
            "comp_op": self.combo_comp_op.currentText(),
            "system_sound_alias": self.combo_system_sound.currentText(),
            "loop_sound": self.check_loop.isChecked(),
            "mute": self.check_mute.isChecked(),
            "sharpness": self.slider_sharpness.value(),
            "scale": self.spin_scale.value(),
            "keep_digits_only": self.check_digits_only.isChecked(),
            "total_alarm_count": self.total_alarm_count
        }
        for rect in self.regions:
            if rect:
                config["regions"].append([rect.x(), rect.y(), rect.width(), rect.height()])
            else:
                config["regions"].append(None)

        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "成功", "配置文件保存成功！")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存配置失败: {e}")

    def load_config(self):
        if not os.path.exists(self.config_file):
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.table.blockSignals(True)
            regions = config.get("regions", [])
            for i, r in enumerate(regions[:10]):
                if r:
                    self.regions[i] = QRect(r[0], r[1], r[2], r[3])
                    self.table.setItem(i, 2, QTableWidgetItem(f"{r[0]}, {r[1]}, {r[2]}, {r[3]}"))
                    btn = self.table.cellWidget(i, 1)
                    if btn:
                        btn.setText("重框选")
                    self.table.setItem(i, 4, QTableWidgetItem("待监控"))
                else:
                    self.regions[i] = None
                    self.table.setItem(i, 2, QTableWidgetItem("未框选"))
            self.table.blockSignals(False)

            self.edit_alarm_value.setText(config.get("alarm_value", ""))
            self.combo_comp_op.setCurrentText(config.get("comp_op", "="))
            self.combo_system_sound.setCurrentText(config.get("system_sound_alias", "SystemExclamation"))
            self.check_loop.setChecked(config.get("loop_sound", False))
            self.check_mute.setChecked(config.get("mute", False))
            self.slider_sharpness.setValue(config.get("sharpness", 0))
            self.spin_scale.setValue(config.get("scale", 1.0))
            self.check_digits_only.setChecked(config.get("keep_digits_only", True))
            self.total_alarm_count = config.get("total_alarm_count", 0)
            self.label_alarm_count.setText(str(self.total_alarm_count))
        except Exception as e:
            self.log(f"加载配置文件时遇到异常: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
