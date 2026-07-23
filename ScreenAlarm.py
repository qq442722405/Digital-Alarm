import sys
import json
import os
import numpy as np
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QLineEdit, QLabel, QFileDialog, QTextEdit, QGroupBox,
    QMessageBox, QSystemTrayIcon, QMenu, QAction, QStyle, QSlider, QDoubleSpinBox,
    QButtonGroup, QRadioButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QIcon
from paddleocr import PaddleOCR
from PIL import Image, ImageEnhance, ImageGrab
import winsound
import ctypes

# ---------- 拖拽式区域选择器 ----------
class RegionSelector(QWidget):
    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        self.rect = QRect()
        self.tip_text = "按住鼠标左键拖拽框选区域（ESC 取消）"

    def show_selector(self, tip_text=""):
        if tip_text:
            self.tip_text = tip_text
        self.start_pos = None
        self.end_pos = None
        self.is_selecting = False
        self.rect = QRect()
        
        # 覆盖全屏
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())
        self.show()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. 绘制全屏半透明遮罩（防止点击穿透，同时提供视觉反馈）
        painter.fillRect(self.rect(), QColor(0, 0, 0, 80))

        # 2. 绘制顶部指引文字
        painter.setPen(QPen(Qt.white))
        font = painter.font()
        font.setPointSize(13)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(30, 50, self.tip_text)

        # 3. 实时绘制选中的框线
        if self.rect.width() > 0 and self.rect.height() > 0:
            # 镂空高亮/红框
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
            painter.setBrush(QColor(255, 0, 0, 40))
            painter.drawRect(self.rect)
            
            # 显示当前选择的宽高尺寸
            info_text = f"{self.rect.width()} x {self.rect.height()}"
            painter.drawText(self.rect.x(), max(20, self.rect.y() - 8), info_text)

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

# ---------- OCR 识别线程 ----------
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
                    # 使用 PIL.ImageGrab 实现线程安全的快速截图
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

# ---------- 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕监控报警工具")
        self.setGeometry(100, 100, 1050, 780)

        # 应用图标处理
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base_path, "1.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScreenMonitorAlarm")
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

        self.sound_mode = "system"
        self.custom_sound_path = ""
        self.loop_sound = False
        self.mute = False
        self.loop_playing = False

        self.sharpness = 0
        self.scale = 1.0
        self.keep_digits_only = True

        self.ocr_thread = None
        self.current_set_row = -1
        self.is_batch_setting = False

        self.selector = RegionSelector()
        self.selector.region_selected.connect(self.on_region_selected)

        self.init_tray()
        self.init_ui()
        self.load_config()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 顶栏按钮
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始监控")
        self.btn_stop = QPushButton("■ 停止监控")
        self.btn_stop.setEnabled(False)
        self.btn_set_all = QPushButton("📐 全部依次框选")
        self.btn_save = QPushButton("💾 保存配置")
        self.btn_load = QPushButton("📂 加载配置")
        self.btn_tray = QPushButton("🔽 最小化托盘")
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_set_all)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_tray)
        main_layout.addLayout(btn_layout)

        # 报警阈值设置
        alarm_group = QGroupBox("报警条件设置（统一共用）")
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

        # 表格配置
        self.table = QTableWidget(10, 4)
        self.table.setHorizontalHeaderLabels(["行号", "框选状态", "实时识别值", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 120)
        self.table.setColumnWidth(2, 140)

        for i in range(10):
            self.table.setItem(i, 0, QTableWidgetItem(f"第 {i+1} 行"))
            btn = QPushButton("拖拽框选")
            btn.clicked.connect(lambda checked, row=i: self.set_single_region(row))
            self.table.setCellWidget(i, 1, btn)
            self.table.setItem(i, 2, QTableWidgetItem(""))
            self.table.setItem(i, 3, QTableWidgetItem("未设置"))
        main_layout.addWidget(self.table)

        # 声音设置
        sound_group = QGroupBox("报警声音")
        sound_layout = QVBoxLayout(sound_group)
        mode_layout = QHBoxLayout()
        self.radio_system = QRadioButton("系统提示音")
        self.radio_custom = QRadioButton("自定义 WAV 声音")
        self.radio_system.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.radio_system, 0)
        mode_group.addButton(self.radio_custom, 1)
        mode_layout.addWidget(self.radio_system)
        mode_layout.addWidget(self.radio_custom)
        mode_layout.addStretch()
        sound_layout.addLayout(mode_layout)

        sys_layout = QHBoxLayout()
        sys_layout.addWidget(QLabel("系统声音:"))
        self.combo_system_sound = QComboBox()
        self.combo_system_sound.addItems(["SystemExclamation", "SystemAsterisk", "SystemHand", "SystemQuestion", "SystemDefault"])
        sys_layout.addWidget(self.combo_system_sound)
        sys_layout.addStretch()
        self.sys_widget = QWidget()
        self.sys_widget.setLayout(sys_layout)
        sound_layout.addWidget(self.sys_widget)

        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("音频文件 (.wav):"))
        self.edit_sound_path = QLineEdit()
        custom_layout.addWidget(self.edit_sound_path)
        self.btn_browse = QPushButton("浏览...")
        custom_layout.addWidget(self.btn_browse)
        self.btn_test_sound = QPushButton("试听")
        custom_layout.addWidget(self.btn_test_sound)
        self.custom_widget = QWidget()
        self.custom_widget.setLayout(custom_layout)
        self.custom_widget.setVisible(False)
        sound_layout.addWidget(self.custom_widget)

        loop_layout = QHBoxLayout()
        self.check_loop = QCheckBox("循环播放声音")
        self.check_mute = QCheckBox("静音（仅显示提示，不播放声音）")
        loop_layout.addWidget(self.check_loop)
        loop_layout.addWidget(self.check_mute)
        loop_layout.addStretch()
        sound_layout.addLayout(loop_layout)
        main_layout.addWidget(sound_group)

        # 预处理选项
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
        preproc_layout.addWidget(QLabel("图像放大倍数:"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(1.0, 4.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(1.0)
        preproc_layout.addWidget(self.spin_scale)

        self.check_digits_only = QCheckBox("仅过滤保留数字与小数点")
        self.check_digits_only.setChecked(True)
        preproc_layout.addSpacing(20)
        preproc_layout.addWidget(self.check_digits_only)
        preproc_layout.addStretch()
        main_layout.addWidget(preproc_group)

        # 报警日志
        log_group = QGroupBox("报警日志与统计")
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
        self.btn_set_all.clicked.connect(self.set_all_regions)
        self.btn_save.clicked.connect(self.save_config)
        self.btn_load.clicked.connect(self.load_config)
        self.btn_tray.clicked.connect(self.hide_to_tray)
        self.radio_system.toggled.connect(self.on_sound_mode_changed)
        self.radio_custom.toggled.connect(self.on_sound_mode_changed)
        self.btn_browse.clicked.connect(self.browse_sound)
        self.btn_test_sound.clicked.connect(self.test_sound)
        self.slider_sharpness.valueChanged.connect(lambda v: self.label_sharpness_val.setText(str(v)))

    def init_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        if getattr(sys, 'frozen', False):
            ico_path = os.path.join(sys._MEIPASS, "1.ico")
        else:
            ico_path = os.path.join(os.path.dirname(__file__), "1.ico")

        if os.path.exists(ico_path):
            self.tray_icon.setIcon(QIcon(ico_path))
        else:
            self.tray_icon.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))

        tray_menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_app)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()

    def hide_to_tray(self):
        self.hide()
        self.tray_icon.showMessage("屏幕监控", "已最小化到系统托盘运行", QSystemTrayIcon.Information, 2000)

    def show_normal(self):
        self.show()
        self.activateWindow()

    def quit_app(self):
        self.stop_monitor()
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide_to_tray()
            event.ignore()
        else:
            self.quit_app()

    def on_sound_mode_changed(self):
        if self.radio_system.isChecked():
            self.sound_mode = "system"
            self.sys_widget.setVisible(True)
            self.custom_widget.setVisible(False)
        else:
            self.sound_mode = "custom"
            self.sys_widget.setVisible(False)
            self.custom_widget.setVisible(True)

    def browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(self, "选择音效", "", "WAV 音频文件 (*.wav)")
        if path:
            self.edit_sound_path.setText(path)

    def test_sound(self):
        if self.sound_mode == "system":
            alias = self.combo_system_sound.currentText()
            try:
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
        else:
            path = self.edit_sound_path.text().strip()
            if path and os.path.exists(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                QMessageBox.warning(self, "提示", "音频文件路径不存在！")

    def play_alarm_sound(self):
        if self.check_mute.isChecked():
            return
        flags = winsound.SND_ASYNC
        if self.check_loop.isChecked():
            flags |= winsound.SND_LOOP

        if self.sound_mode == "system":
            alias = self.combo_system_sound.currentText()
            winsound.PlaySound(alias, winsound.SND_ALIAS | flags)
        else:
            path = self.edit_sound_path.text().strip()
            if path and os.path.exists(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | flags)

    def stop_alarm_sound(self):
        winsound.PlaySound(None, winsound.SND_PURGE)

    # ---------- 区域框选交互逻辑 ----------
    def set_single_region(self, row):
        self.is_batch_setting = False
        self.current_set_row = row
        tip = f"【单行设置】请按住鼠标左键，拖拽框选【第 {row+1} 行】的识别区域"
        self.selector.show_selector(tip)

    def set_all_regions(self):
        self.is_batch_setting = True
        self.current_set_row = 0
        self.prompt_next_batch_region()

    def prompt_next_batch_region(self):
        if self.current_set_row < 10:
            tip = f"【批量设置 {self.current_set_row + 1}/10】请按住鼠标左键拖拽框选区域（按 ESC 可跳过）"
            self.selector.show_selector(tip)
        else:
            self.is_batch_setting = False
            QMessageBox.information(self, "完成", "所有 10 个识别区域均已设置完成！")

    def on_region_selected(self, rect):
        if 0 <= self.current_set_row < 10:
            self.regions[self.current_set_row] = rect
            btn = self.table.cellWidget(self.current_set_row, 1)
            if btn:
                btn.setText("已框选 ✅")
            self.table.item(self.current_set_row, 3).setText("待监控")

        if self.is_batch_setting:
            self.current_set_row += 1
            self.prompt_next_batch_region()

    # ---------- 监控流程 ----------
    def start_monitor(self):
        if all(r is None for r in self.regions):
            QMessageBox.warning(self, "提示", "请至少框选设置 1 个识别区域！")
            return

        if self.ocr is None:
            self.log("正在加载 PaddleOCR 引擎，请稍候...")
            QApplication.processEvents()
            try:
                self.ocr = PaddleOCR(use_angle_cls=False, lang='ch', show_log=False)
                self.log("OCR 引擎加载成功。")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"无法加载 PaddleOCR: {e}")
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
            self.table.item(i, 2).setText(text)

            if not text or self.regions[i] is None:
                if self.regions[i] is not None:
                    self.table.item(i, 3).setText("监测中...")
                self.debounce_counts[i] = 0
                continue

            try:
                current_val = float(text)
            except ValueError:
                self.table.item(i, 3).setText("非有效数字")
                self.debounce_counts[i] = 0
                continue

            if not self.alarm_value:
                self.table.item(i, 3).setText("未设报警值")
                self.debounce_counts[i] = 0
                continue

            try:
                alarm_val = float(self.alarm_value)
            except ValueError:
                self.table.item(i, 3).setText("阈值无效")
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
                    self.table.item(i, 3).setText("⚠️ 报警触发！")
                    alarm_triggered = True
                    alarm_rows.append(i + 1)
                else:
                    self.table.item(i, 3).setText("疑似超限...")
            else:
                self.debounce_counts[i] = 0
                self.table.item(i, 3).setText("正常")

        if alarm_triggered:
            if not self.alarm_active:
                self.play_alarm_sound()
                self.alarm_active = True
                self.total_alarm_count += 1
                self.label_alarm_count.setText(str(self.total_alarm_count))
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                self.log(f"[{now}] 🚨 触发报警！行号: {alarm_rows} | 触发设定条件: {self.comp_op} {self.alarm_value}")
        else:
            if self.alarm_active:
                self.stop_alarm_sound()
                self.alarm_active = False

    def log(self, message):
        self.log_text.append(message)

    # ---------- 配置导入与导出 ----------
    def save_config(self):
        config = {
            "regions": [],
            "alarm_value": self.edit_alarm_value.text(),
            "comp_op": self.combo_comp_op.currentText(),
            "sound_mode": self.sound_mode,
            "system_sound_alias": self.combo_system_sound.currentText(),
            "custom_sound_path": self.edit_sound_path.text(),
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

            regions = config.get("regions", [])
            for i, r in enumerate(regions[:10]):
                if r:
                    self.regions[i] = QRect(r[0], r[1], r[2], r[3])
                    btn = self.table.cellWidget(i, 1)
                    if btn:
                        btn.setText("已框选 ✅")
                    self.table.item(i, 3).setText("待监控")
                else:
                    self.regions[i] = None

            self.edit_alarm_value.setText(config.get("alarm_value", ""))
            self.combo_comp_op.setCurrentText(config.get("comp_op", "="))
            self.sound_mode = config.get("sound_mode", "system")
            if self.sound_mode == "system":
                self.radio_system.setChecked(True)
            else:
                self.radio_custom.setChecked(True)

            self.combo_system_sound.setCurrentText(config.get("system_sound_alias", "SystemExclamation"))
            self.edit_sound_path.setText(config.get("custom_sound_path", ""))
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
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
