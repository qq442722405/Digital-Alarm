import sys
import json
import os
import numpy as np
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QComboBox, QCheckBox,
    QLineEdit, QLabel, QFileDialog, QTextEdit, QGroupBox, QGridLayout,
    QMessageBox, QSystemTrayIcon, QMenu, QAction, QStyle, QSlider, QDoubleSpinBox,
    QButtonGroup, QRadioButton
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QIcon
from paddleocr import PaddleOCR
from PIL import Image, ImageEnhance
import winsound
import ctypes

# ---------- 区域选择器（左上→右下）----------
class RegionSelector(QWidget):
    region_selected = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.showFullScreen()
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background:transparent;")
        self.setCursor(Qt.CrossCursor)
        self.first_point = None
        self.second_point = None
        self.rect = None

    def paintEvent(self, event):
        if self.rect:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
            painter.setBrush(QColor(255, 0, 0, 50))
            painter.drawRect(self.rect)
        elif self.first_point:
            painter = QPainter(self)
            painter.setPen(QPen(QColor(255, 0, 0), 2, Qt.DashLine))
            painter.drawLine(self.first_point.x()-10, self.first_point.y(),
                             self.first_point.x()+10, self.first_point.y())
            painter.drawLine(self.first_point.x(), self.first_point.y()-10,
                             self.first_point.x(), self.first_point.y()+10)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self.first_point:
                self.first_point = event.pos()
                self.update()
            elif not self.second_point:
                self.second_point = event.pos()
                self.rect = QRect(self.first_point, self.second_point).normalized()
                self.update()
                if self.rect.width() > 5 and self.rect.height() > 5:
                    self.region_selected.emit(self.rect)
                    self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.first_point = None
            self.second_point = None
            self.rect = None
            self.update()
            self.hide()

# ---------- OCR 线程 ----------
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
            screen = QApplication.primaryScreen()
            if not screen:
                self.msleep(100)
                continue
            pixmap = screen.grabWindow(0)
            for i, rect in enumerate(self.regions):
                if rect is None or rect.width() < 5:
                    results.append("")
                    continue
                cropped = pixmap.copy(rect)
                if cropped.isNull():
                    results.append("")
                    continue
                qimg = cropped.toImage().convertToFormat(4)
                ptr = qimg.bits()
                ptr.setsize(qimg.byteCount())
                arr = np.array(ptr).reshape(qimg.height(), qimg.width(), 4)
                img_pil = Image.fromarray(arr[..., :3], 'RGB')
                img_pil = self.preprocess(img_pil)
                try:
                    ocr_result = self.ocr.ocr(np.array(img_pil), cls=False)
                    if ocr_result and ocr_result[0]:
                        text = " ".join([line[1][0] for line in ocr_result[0]])
                    else:
                        text = ""
                except Exception:
                    text = ""
                if self.keep_digits_only:
                    allowed = set("0123456789.")
                    text = "".join([c for c in text if c in allowed])
                results.append(text.strip())
            self.result_signal.emit(results)
            self.msleep(200)

    def stop(self):
        self.running = False

# ---------- 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕监控报警工具")
        self.setGeometry(100, 100, 1100, 800)

        # 程序图标（兼容打包后路径）
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base_path, "1.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ScreenMonitorAlarm")

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
        self.system_sound_alias = "SystemExclamation"
        self.custom_sound_path = ""
        self.loop_sound = False
        self.mute = False
        self.loop_playing = False

        self.sharpness = 0
        self.scale = 1.0
        self.keep_digits_only = True

        self.ocr_thread = None
        self.selector = None
        self.current_set_row = -1

        self.tray_icon = None
        self.init_tray()
        self.init_ui()
        self.load_config()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 控制按钮
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("▶ 开始监控")
        self.btn_stop = QPushButton("■ 停止监控")
        self.btn_stop.setEnabled(False)
        self.btn_set_all = QPushButton("📐 全部设置区域")
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

        # 统一报警值
        alarm_group = QGroupBox("报警条件（所有行共用）")
        alarm_layout = QHBoxLayout(alarm_group)
        alarm_layout.addWidget(QLabel("报警值:"))
        self.edit_alarm_value = QLineEdit()
        self.edit_alarm_value.setPlaceholderText("输入报警数值")
        self.edit_alarm_value.setMaximumWidth(100)
        alarm_layout.addWidget(self.edit_alarm_value)
        alarm_layout.addWidget(QLabel("条件:"))
        self.combo_comp_op = QComboBox()
        self.combo_comp_op.addItems(["=", ">", "<", "≥", "≤"])
        alarm_layout.addWidget(self.combo_comp_op)
        alarm_layout.addStretch()
        main_layout.addWidget(alarm_group)

        # 行表格（含每行设置区域按钮）
        self.table = QTableWidget(10, 4)
        self.table.setHorizontalHeaderLabels(["行号", "设置区域", "当前值", "状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 100)
        for i in range(10):
            self.table.setItem(i, 0, QTableWidgetItem(str(i+1)))
            btn = QPushButton("框选区域")
            btn.clicked.connect(lambda checked, row=i: self.set_single_region(row))
            self.table.setCellWidget(i, 1, btn)
            self.table.setItem(i, 2, QTableWidgetItem(""))
            self.table.setItem(i, 3, QTableWidgetItem("正常"))
        main_layout.addWidget(self.table)

        # 声音设置
        sound_group = QGroupBox("报警声音设置")
        sound_layout = QVBoxLayout(sound_group)
        mode_layout = QHBoxLayout()
        self.radio_system = QRadioButton("系统声音")
        self.radio_custom = QRadioButton("自定义声音")
        self.radio_system.setChecked(True)
        mode_group = QButtonGroup(self)
        mode_group.addButton(self.radio_system, 0)
        mode_group.addButton(self.radio_custom, 1)
        mode_layout.addWidget(self.radio_system)
        mode_layout.addWidget(self.radio_custom)
        mode_layout.addStretch()
        sound_layout.addLayout(mode_layout)

        sys_layout = QHBoxLayout()
        sys_layout.addWidget(QLabel("选择系统声音:"))
        self.combo_system_sound = QComboBox()
        self.combo_system_sound.addItems(["SystemAsterisk", "SystemExclamation", "SystemHand", "SystemQuestion", "SystemDefault"])
        self.combo_system_sound.setCurrentText("SystemExclamation")
        sys_layout.addWidget(self.combo_system_sound)
        sys_layout.addStretch()
        self.sys_widget = QWidget()
        self.sys_widget.setLayout(sys_layout)
        sound_layout.addWidget(self.sys_widget)

        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("声音文件 (.wav):"))
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
        self.check_loop = QCheckBox("循环播放")
        self.check_mute = QCheckBox("静音（不播放声音）")
        loop_layout.addWidget(self.check_loop)
        loop_layout.addWidget(self.check_mute)
        loop_layout.addStretch()
        sound_layout.addLayout(loop_layout)
        main_layout.addWidget(sound_group)

        # 图像预处理
        preproc_group = QGroupBox("图像预处理（识别锐化与放大）")
        preproc_layout = QVBoxLayout(preproc_group)
        sharp_layout = QHBoxLayout()
        sharp_layout.addWidget(QLabel("锐化强度:"))
        self.slider_sharpness = QSlider(Qt.Horizontal)
        self.slider_sharpness.setRange(0, 100)
        self.slider_sharpness.setValue(0)
        sharp_layout.addWidget(self.slider_sharpness)
        self.label_sharpness_val = QLabel("0")
        sharp_layout.addWidget(self.label_sharpness_val)
        preproc_layout.addLayout(sharp_layout)
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("放大倍数:"))
        self.spin_scale = QDoubleSpinBox()
        self.spin_scale.setRange(1.0, 4.0)
        self.spin_scale.setSingleStep(0.1)
        self.spin_scale.setValue(1.0)
        scale_layout.addWidget(self.spin_scale)
        scale_layout.addStretch()
        preproc_layout.addLayout(scale_layout)
        self.check_digits_only = QCheckBox("只保留数字和小数点")
        self.check_digits_only.setChecked(True)
        preproc_layout.addWidget(self.check_digits_only)
        main_layout.addWidget(preproc_group)

        # 报警次数与日志
        log_group = QGroupBox("报警记录")
        log_layout = QVBoxLayout(log_group)
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("报警总次数:"))
        self.label_alarm_count = QLabel("0")
        count_layout.addWidget(self.label_alarm_count)
        count_layout.addStretch()
        log_layout.addLayout(count_layout)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        main_layout.addWidget(log_group)

        # 信号绑定
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
        self.check_loop.stateChanged.connect(lambda state: setattr(self, 'loop_sound', state == Qt.Checked))
        self.check_mute.stateChanged.connect(lambda state: setattr(self, 'mute', state == Qt.Checked))

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
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_normal()

    def hide_to_tray(self):
        self.hide()
        self.tray_icon.showMessage("屏幕监控", "程序已最小化到系统托盘", QSystemTrayIcon.Information, 2000)

    def show_normal(self):
        self.show()
        self.setWindowState(Qt.WindowActive)

    def quit_app(self):
        if self.ocr_thread and self.ocr_thread.isRunning():
            self.ocr_thread.stop()
            self.ocr_thread.wait()
        self.stop_alarm_sound()
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
        path, _ = QFileDialog.getOpenFileName(self, "选择声音文件", os.path.join(os.environ["WINDIR"], "Media"), "WAV 文件 (*.wav)")
        if path:
            self.edit_sound_path.setText(path)

    def test_sound(self):
        if self.sound_mode == "system":
            alias = self.combo_system_sound.currentText()
            try:
                winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
            except:
                pass
        else:
            path = self.edit_sound_path.text().strip()
            if path and os.path.exists(path):
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                QMessageBox.warning(self, "错误", "声音文件不存在")

    def play_alarm_sound(self):
        if self.mute:
            return
        if self.sound_mode == "system":
            alias = self.combo_system_sound.currentText()
            flags = winsound.SND_ALIAS | winsound.SND_ASYNC
            if self.loop_sound:
                flags |= winsound.SND_LOOP
            winsound.PlaySound(alias, flags)
            self.loop_playing = self.loop_sound
        else:
            path = self.edit_sound_path.text().strip()
            if not path or not os.path.exists(path):
                return
            flags = winsound.SND_FILENAME | winsound.SND_ASYNC
            if self.loop_sound:
                flags |= winsound.SND_LOOP
            winsound.PlaySound(path, flags)
            self.loop_playing = self.loop_sound

    def stop_alarm_sound(self):
        if self.loop_playing:
            winsound.PlaySound(None, winsound.SND_PURGE)
            self.loop_playing = False

    # ---------- 区域设置 ----------
    def set_single_region(self, row):
        self.current_set_row = row
        self.selector = RegionSelector()
        self.selector.region_selected.connect(self.on_single_region_selected)
        self.selector.show()
        QMessageBox.information(self, "提示", f"请点击第 {row+1} 行的【左上角】，再点击【右下角】")

    def on_single_region_selected(self, rect):
        if 0 <= self.current_set_row < 10:
            self.regions[self.current_set_row] = rect
            QMessageBox.information(self, "完成", f"第 {self.current_set_row+1} 行区域已设置")
        self.current_set_row = -1

    def set_all_regions(self):
        self.current_set_row = 0
        self.selector = RegionSelector()
        self.selector.region_selected.connect(self.on_all_region_selected)
        self.selector.show()
        QMessageBox.information(self, "提示", f"请设置第 {self.current_set_row+1} 行区域（左上→右下），按 ESC 跳过")

    def on_all_region_selected(self, rect):
        if 0 <= self.current_set_row < 10:
            self.regions[self.current_set_row] = rect
            self.current_set_row += 1
            if self.current_set_row < 10:
                QMessageBox.information(self, "提示", f"请设置第 {self.current_set_row+1} 行区域")
                self.selector.show()
            else:
                self.selector.close()
                QMessageBox.information(self, "完成", "10个区域已全部设置完毕")
                self.current_set_row = -1
        else:
            self.selector.close()

    # ---------- 监控 ----------
    def start_monitor(self):
        if all(r is None for r in self.regions):
            QMessageBox.warning(self, "错误", "至少需要设置一个识别区域！")
            return
        if self.ocr is None:
            try:
                self.ocr = PaddleOCR(use_angle_cls=False, lang='ch', show_log=False)
            except Exception as e:
                QMessageBox.critical(self, "OCR 错误", f"无法加载 OCR 引擎: {e}")
                return

        self.alarm_value = self.edit_alarm_value.text().strip()
        self.comp_op = self.combo_comp_op.currentText()
        self.sharpness = self.slider_sharpness.value()
        self.scale = self.spin_scale.value()
        self.keep_digits_only = self.check_digits_only.isChecked()

        if self.ocr_thread and self.ocr_thread.isRunning():
            self.ocr_thread.stop()
            self.ocr_thread.wait()
        self.ocr_thread = OCRWorker(
            self.regions, self.ocr,
            sharpness=self.sharpness,
            scale=self.scale,
            keep_digits_only=self.keep_digits_only
        )
        self.ocr_thread.result_signal.connect(self.process_results)
        self.ocr_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log("监控已启动。")

    def stop_monitor(self):
        if self.ocr_thread:
            self.ocr_thread.stop()
            self.ocr_thread.wait()
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.stop_alarm_sound()
        self.alarm_active = False
        self.log("监控已停止。")

    def process_results(self, results):
        alarm_triggered = False
        for i, text in enumerate(results):
            if i >= 10:
                break
            self.table.item(i, 2).setText(text)
            if not text:
                self.table.item(i, 3).setText("正常")
                self.debounce_counts[i] = 0
                continue
            try:
                current_val = float(text)
            except ValueError:
                self.table.item(i, 3).setText("无效")
                self.debounce_counts[i] = 0
                continue

            if not self.alarm_value:
                self.table.item(i, 3).setText("正常")
                self.debounce_counts[i] = 0
                continue
            try:
                alarm_val = float(self.alarm_value)
            except ValueError:
                self.table.item(i, 3).setText("报警值无效")
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
                    self.table.item(i, 3).setText("报警！")
                    alarm_triggered = True
                else:
                    self.table.item(i, 3).setText("疑似...")
            else:
                self.debounce_counts[i] = 0
                self.table.item(i, 3).setText("正常")

        if alarm_triggered and not self.mute:
            if not self.alarm_active:
                self.play_alarm_sound()
                self.alarm_active = True
                self.total_alarm_count += 1
                self.label_alarm_count.setText(str(self.total_alarm_count))
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                alarm_rows = [i+1 for i in range(10) if self.table.item(i,3).text() == "报警！"]
                self.log(f"{now} - 行 {alarm_rows} 报警触发，当前报警值: {self.alarm_value}")
        elif not alarm_triggered and self.alarm_active:
            self.stop_alarm_sound()
            self.alarm_active = False

    def log(self, message):
        self.log_text.append(message)

    # ---------- 配置 ----------
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
            "debounce_threshold": self.debounce_threshold,
            "total_alarm_count": self.total_alarm_count
        }
        for rect in self.regions:
            if rect:
                config["regions"].append([rect.x(), rect.y(), rect.width(), rect.height()])
            else:
                config["regions"].append(None)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        QMessageBox.information(self, "成功", "配置已保存。")

    def load_config(self):
        if not os.path.exists(self.config_file):
            return
        with open(self.config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        regions = config.get("regions", [])
        for i, r in enumerate(regions[:10]):
            if r and i < 10:
                self.regions[i] = QRect(r[0], r[1], r[2], r[3])
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
        self.debounce_threshold = config.get("debounce_threshold", 3)
        self.total_alarm_count = config.get("total_alarm_count", 0)
        self.label_alarm_count.setText(str(self.total_alarm_count))

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())