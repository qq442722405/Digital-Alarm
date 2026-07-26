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
    QButtonGroup, QRadioButton, QHeaderView, QAbstractItemView
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect
from PyQt5.QtGui import QPainter, QPen, QColor, QIcon
import ctypes
import winsound

# 动态导入 PaddleOCR，避免打包前导入失败
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_READY = True
except Exception:
    PADDLEOCR_READY = False

from PIL import Image, ImageEnhance

# ------------------- 区域选择器（左上→右下） -------------------
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

# ------------------- 检测行数据结构 -------------------
class DetectRow:
    def __init__(self, rect=None, alarm_value="", comp_op="="):
        self.rect = rect          # QRect
        self.alarm_value = alarm_value  # str
        self.comp_op = comp_op    # "=", ">", "<", "≥", "≤"
        self.current_text = ""    # 当前识别文本
        self.state = "正常"       # 正常/报警/疑似...
        self.debounce = 0
        self.enabled = True       # 是否启用检测（默认启用）

# ------------------- OCR 检测线程（逐行循环） -------------------
class DetectWorker(QThread):
    update_result = pyqtSignal(int, str, str)   # row_index, current_text, state
    alarm_triggered = pyqtSignal(int)           # 某行触发报警

    def __init__(self, rows, sharpness=0, scale=1.0, keep_digits_only=True, interval=500):
        super().__init__()
        self.rows = rows            # list of DetectRow
        self.sharpness = sharpness
        self.scale = scale
        self.keep_digits_only = keep_digits_only
        self.interval = interval    # 每行检测间隔（毫秒）
        self.running = False
        self.ocr = None

    def init_ocr(self):
        if not PADDLEOCR_READY:
            raise RuntimeError("PaddleOCR 不可用")
        try:
            self.ocr = PaddleOCR(lang='ch', show_log=False)
        except Exception as e:
            raise RuntimeError(f"初始化 OCR 失败: {e}")

    def preprocess(self, img_pil):
        if self.sharpness > 0:
            enhancer = ImageEnhance.Sharpness(img_pil)
            img_pil = enhancer.enhance(1.0 + self.sharpness / 100.0 * 2.0)
        if self.scale != 1.0:
            w, h = img_pil.size
            img_pil = img_pil.resize((int(w * self.scale), int(h * self.scale)), Image.LANCZOS)
        return img_pil

    def run(self):
        if self.ocr is None:
            self.init_ocr()
        self.running = True
        screen = QApplication.primaryScreen()
        if not screen:
            return

        while self.running:
            for row_index, row in enumerate(self.rows):
                if not self.running:
                    break
                if not row.enabled or row.rect is None:
                    continue
                # 截图区域
                pixmap = screen.grabWindow(0)
                cropped = pixmap.copy(row.rect)
                qimg = cropped.toImage().convertToFormat(4)
                ptr = qimg.bits()
                ptr.setsize(qimg.byteCount())
                arr = np.array(ptr).reshape(qimg.height(), qimg.width(), 4)
                img_pil = Image.fromarray(arr[..., :3], 'RGB')
                img_pil = self.preprocess(img_pil)
                # OCR
                try:
                    result = self.ocr.ocr(np.array(img_pil), cls=False)
                    if result and result[0]:
                        text = " ".join([line[1][0] for line in result[0]])
                    else:
                        text = ""
                except Exception:
                    text = ""
                if self.keep_digits_only:
                    allowed = set("0123456789.")
                    text = "".join([c for c in text if c in allowed])
                row.current_text = text.strip()

                # 报警判断
                alarm_value_str = row.alarm_value
                state = "正常"
                if text and alarm_value_str:
                    try:
                        current_val = float(text)
                        alarm_val = float(alarm_value_str)
                    except ValueError:
                        state = "无效"
                    else:
                        op = row.comp_op
                        if op == "=":
                            met = abs(current_val - alarm_val) < 1e-6
                        elif op == ">":
                            met = current_val > alarm_val
                        elif op == "<":
                            met = current_val < alarm_val
                        elif op == "≥":
                            met = current_val >= alarm_val
                        elif op == "≤":
                            met = current_val <= alarm_val
                        if met:
                            row.debounce += 1
                            if row.debounce >= 3:
                                state = "报警！"
                        else:
                            row.debounce = 0
                else:
                    row.debounce = 0

                row.state = state
                self.update_result.emit(row_index, row.current_text, state)
                if state == "报警！":
                    self.alarm_triggered.emit(row_index)
                # 行间延迟
                self.msleep(self.interval)

    def stop(self):
        self.running = False

# ------------------- 主窗口 -------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("数字报警")
        self.setGeometry(100, 100, 1200, 700)

        # 图标
        if getattr(sys, 'frozen', False):
            base_path = sys._MEIPASS
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
        ico_path = os.path.join(base_path, "1.ico")
        if os.path.exists(ico_path):
            self.setWindowIcon(QIcon(ico_path))
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DigitalAlarm")

        self.config_file = "config.json"
        self.detect_rows = []       # 存放 DetectRow 对象
        self.detect_thread = None

        # 声音设置
        self.sound_mode = "system"      # system / custom
        self.system_sound_alias = "SystemExclamation"
        self.custom_sound_path = ""
        self.loop_sound = False
        self.mute = False
        self.loop_playing = False

        # 图像预处理
        self.sharpness = 0
        self.scale = 1.0
        self.keep_digits_only = True
        self.detect_interval = 200      # 每行检测间隔（ms）

        # 报警计数
        self.total_alarm_count = 0

        self.tray_icon = None
        self.init_tray()
        self.init_ui()
        self.load_config()
        # 如果没有配置行，默认添加一行
        if not self.detect_rows:
            self.add_row()

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # 顶部操作按钮
        top_btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("➕ 添加检测行")
        self.btn_del = QPushButton("❌ 删除选中行")
        self.btn_start = QPushButton("▶ 开始监控")
        self.btn_stop = QPushButton("■ 停止监控")
        self.btn_stop.setEnabled(False)
        self.btn_save = QPushButton("💾 保存配置")
        self.btn_load = QPushButton("📂 加载配置")
        self.btn_tray = QPushButton("🔽 最小化托盘")
        top_btn_layout.addWidget(self.btn_add)
        top_btn_layout.addWidget(self.btn_del)
        top_btn_layout.addWidget(self.btn_start)
        top_btn_layout.addWidget(self.btn_stop)
        top_btn_layout.addWidget(self.btn_save)
        top_btn_layout.addWidget(self.btn_load)
        top_btn_layout.addWidget(self.btn_tray)
        main_layout.addLayout(top_btn_layout)

        # 检测行表格
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["行号", "区域设置", "报警值", "条件", "当前值", "状态"])
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(1, 80)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 80)
        self.table.setColumnWidth(4, 80)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked)
        main_layout.addWidget(self.table)

        # 全局声音设置
        sound_group = QGroupBox("报警声音设置（全局）")
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

        # 日志
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

        # 信号连接
        self.btn_add.clicked.connect(self.add_row)
        self.btn_del.clicked.connect(self.delete_selected_row)
        self.btn_start.clicked.connect(self.start_monitor)
        self.btn_stop.clicked.connect(self.stop_monitor)
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
        self.tray_icon.showMessage("数字报警", "程序已最小化到系统托盘", QSystemTrayIcon.Information, 2000)

    def show_normal(self):
        self.show()
        self.setWindowState(Qt.WindowActive)

    def quit_app(self):
        if self.detect_thread and self.detect_thread.isRunning():
            self.detect_thread.stop()
            self.detect_thread.wait(2000)
        self.stop_alarm_sound()
        self.tray_icon.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide_to_tray()
            event.ignore()
        else:
            self.quit_app()

    # ---------- 行管理 ----------
    def add_row(self):
        row = DetectRow()
        self.detect_rows.append(row)
        self.update_table_row(len(self.detect_rows)-1)
        # 自动编号
        self.refresh_row_numbers()

    def delete_selected_row(self):
        selected = self.table.selectionModel().selectedRows()
        if not selected:
            QMessageBox.warning(self, "提示", "请先选择要删除的行")
            return
        # 倒序删除，避免索引错乱
        indices = sorted([idx.row() for idx in selected], reverse=True)
        for idx in indices:
            del self.detect_rows[idx]
            self.table.removeRow(idx)
        self.refresh_row_numbers()

    def update_table_row(self, index):
        """根据 detect_rows[index] 更新表格的行"""
        row = self.detect_rows[index]
        if self.table.rowCount() <= index:
            self.table.insertRow(index)
        # 列0：行号（稍后统一刷新）
        # 列1：区域设置按钮
        btn = QPushButton("框选区域")
        btn.clicked.connect(lambda checked, idx=index: self.set_region_for_row(idx))
        self.table.setCellWidget(index, 1, btn)
        # 列2：报警值（可编辑）
        item_alarm = QTableWidgetItem(row.alarm_value)
        self.table.setItem(index, 2, item_alarm)
        # 列3：条件（下拉框）
        combo = QComboBox()
        combo.addItems(["=", ">", "<", "≥", "≤"])
        combo.setCurrentText(row.comp_op)
        combo.currentTextChanged.connect(lambda text, idx=index: self.on_comp_changed(idx, text))
        self.table.setCellWidget(index, 3, combo)
        # 列4：当前值
        self.table.setItem(index, 4, QTableWidgetItem(row.current_text))
        # 列5：状态
        self.table.setItem(index, 5, QTableWidgetItem(row.state))

    def refresh_row_numbers(self):
        for i in range(self.table.rowCount()):
            self.table.setItem(i, 0, QTableWidgetItem(str(i+1)))

    def set_region_for_row(self, index):
        self.current_set_row = index
        self.selector = RegionSelector()
        self.selector.region_selected.connect(self.on_region_selected_for_row)
        self.selector.show()
        QMessageBox.information(self, "提示", f"请在第 {index+1} 行点击【左上角】，再点击【右下角】")

    def on_region_selected_for_row(self, rect):
        if hasattr(self, 'current_set_row') and 0 <= self.current_set_row < len(self.detect_rows):
            self.detect_rows[self.current_set_row].rect = rect
            QMessageBox.information(self, "完成", f"第 {self.current_set_row+1} 行区域已设置")
        self.current_set_row = -1

    def on_comp_changed(self, index, text):
        if 0 <= index < len(self.detect_rows):
            self.detect_rows[index].comp_op = text

    # ---------- 声音控制 ----------
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

    # ---------- 监控控制 ----------
    def start_monitor(self):
        # 检查至少有一行设置了区域
        valid = any(row.rect is not None for row in self.detect_rows)
        if not valid:
            QMessageBox.warning(self, "错误", "至少需要设置一个识别区域！")
            return

        # 从界面读取每行的报警值和条件
        for i, row in enumerate(self.detect_rows):
            item = self.table.item(i, 2)
            if item:
                row.alarm_value = item.text()
            combo = self.table.cellWidget(i, 3)
            if combo:
                row.comp_op = combo.currentText()

        self.sharpness = self.slider_sharpness.value()
        self.scale = self.spin_scale.value()
        self.keep_digits_only = self.check_digits_only.isChecked()

        if self.detect_thread and self.detect_thread.isRunning():
            self.detect_thread.stop()
            self.detect_thread.wait(2000)

        self.detect_thread = DetectWorker(
            self.detect_rows,
            sharpness=self.sharpness,
            scale=self.scale,
            keep_digits_only=self.keep_digits_only,
            interval=self.detect_interval
        )
        self.detect_thread.update_result.connect(self.on_update_result)
        self.detect_thread.alarm_triggered.connect(self.on_alarm_triggered)
        self.detect_thread.start()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log("监控已启动。")

    def stop_monitor(self):
        if self.detect_thread:
            self.detect_thread.stop()
            self.detect_thread.wait(2000)
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.stop_alarm_sound()
        self.log("监控已停止。")

    def on_update_result(self, index, current_text, state):
        if 0 <= index < self.table.rowCount():
            self.table.item(index, 4).setText(current_text)
            self.table.item(index, 5).setText(state)

    def on_alarm_triggered(self, index):
        if not self.mute:
            self.play_alarm_sound()
        self.total_alarm_count += 1
        self.label_alarm_count.setText(str(self.total_alarm_count))
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"{now} - 行 {index+1} 触发报警，值: {self.detect_rows[index].current_text}")

    def log(self, message):
        self.log_text.append(message)

    # ---------- 配置存取 ----------
    def save_config(self):
        config = {
            "rows": [],
            "sound_mode": self.sound_mode,
            "system_sound_alias": self.combo_system_sound.currentText(),
            "custom_sound_path": self.edit_sound_path.text(),
            "loop_sound": self.check_loop.isChecked(),
            "mute": self.check_mute.isChecked(),
            "sharpness": self.slider_sharpness.value(),
            "scale": self.spin_scale.value(),
            "keep_digits_only": self.check_digits_only.isChecked(),
            "detect_interval": self.detect_interval,
            "total_alarm_count": self.total_alarm_count
        }
        for row in self.detect_rows:
            r = None
            if row.rect:
                r = [row.rect.x(), row.rect.y(), row.rect.width(), row.rect.height()]
            config["rows"].append({
                "rect": r,
                "alarm_value": row.alarm_value,
                "comp_op": row.comp_op
            })
        try:
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            QMessageBox.information(self, "成功", "配置已保存。")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存失败: {e}")

    def load_config(self):
        if not os.path.exists(self.config_file):
            return
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            self.detect_rows.clear()
            self.table.setRowCount(0)
            rows_data = config.get("rows", [])
            for d in rows_data:
                rect = None
                if d.get("rect"):
                    x, y, w, h = d["rect"]
                    rect = QRect(x, y, w, h)
                row = DetectRow(rect=rect, alarm_value=d.get("alarm_value", ""), comp_op=d.get("comp_op", "="))
                self.detect_rows.append(row)
                self.update_table_row(len(self.detect_rows)-1)
            self.refresh_row_numbers()
            # 声音设置
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
            self.detect_interval = config.get("detect_interval", 200)
            self.total_alarm_count = config.get("total_alarm_count", 0)
            self.label_alarm_count.setText(str(self.total_alarm_count))
        except Exception as e:
            QMessageBox.warning(self, "错误", f"配置加载失败: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())