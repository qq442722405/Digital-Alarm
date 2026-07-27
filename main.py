import io
import os
import re
import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from PIL import ImageGrab
import ddddocr
import pyperclip
import winsound

# ==================== Windows 高分屏 (DPI) 适配 ====================
if sys.platform.startswith('win'):
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDpiAware()
        except Exception:
            pass


def resource_path(relative_path):
    """ 获取静态资源（如图标）绝对路径 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)


class ScreenOCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数字报警器 v3.0 (多数字增强版)")
        self.root.geometry("440x550")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        # 初始化参数与变量
        self.bbox = None            # 框选区域 (x1, y1, x2, y2)
        self.is_monitoring = False  # 监控状态
        self.alarm_count = 0        # 报警统计次数

        # UI 绑定变量
        self.target_nums_var = tk.StringVar(value="88, 100") # 默认目标数字
        self.interval_var = tk.StringVar(value="2.0")       # 默认间隔(秒)
        self.sound_choice_var = tk.StringVar(value="急促蜂鸣") # 默认声音
        self.mute_var = tk.BooleanVar(value=False)          # 静音状态

        # 双引擎初始化：常规识别 + 智能区域检测切块
        try:
            self.ocr = ddddocr.DdddOcr(show_ad=False)
            self.det = ddddocr.DdddOcr(det=True, show_ad=False)
        except Exception as e:
            messagebox.showerror("初始化错误", f"OCR引擎加载失败: {e}")

        # 加载图标
        ico_file = resource_path("1.ico")
        if os.path.exists(ico_file):
            try:
                self.root.iconbitmap(ico_file)
            except Exception:
                pass

        # 窗口关闭事件处理
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 构建界面UI
        self.create_widgets()

    def create_widgets(self):
        # 1. 区域框选模块
        frame_area = tk.LabelFrame(self.root, text=" 1. 监控区域设置 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=8)
        frame_area.pack(fill="x", padx=15, pady=5)

        self.btn_select = tk.Button(
            frame_area, text="🔍 框选/重选表格区域 (支持多数字多行)", command=self.start_selection,
            font=("Microsoft YaHei", 10, "bold"), bg="#007ACC", fg="white", relief="flat", cursor="hand2"
        )
        self.btn_select.pack(fill="x", pady=2)

        self.lbl_area_status = tk.Label(frame_area, text="当前未选择区域", font=("Microsoft YaHei", 9), fg="#888888")
        self.lbl_area_status.pack(pady=2)

        # 2. 规则与参数设置模块
        frame_rules = tk.LabelFrame(self.root, text=" 2. 报警规则与间隔 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=8)
        frame_rules.pack(fill="x", padx=15, pady=5)

        f_target = tk.Frame(frame_rules)
        f_target.pack(fill="x", pady=3)
        tk.Label(f_target, text="目标数字:", font=("Microsoft YaHei", 9), width=10, anchor="w").pack(side="left")
        entry_target = tk.Entry(f_target, textvariable=self.target_nums_var, font=("Microsoft YaHei", 9))
        entry_target.pack(side="left", fill="x", expand=True)
        tk.Label(f_target, text=" (逗号隔开)", font=("Microsoft YaHei", 8), fg="#888888").pack(side="left")

        f_interval = tk.Frame(frame_rules)
        f_interval.pack(fill="x", pady=3)
        tk.Label(f_interval, text="监控间隔(秒):", font=("Microsoft YaHei", 9), width=10, anchor="w").pack(side="left")
        entry_interval = tk.Entry(f_interval, textvariable=self.interval_var, font=("Microsoft YaHei", 9), width=10)
        entry_interval.pack(side="left")

        # 3. 声音与静音控制模块
        frame_sound = tk.LabelFrame(self.root, text=" 3. 报警声音配置 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=8)
        frame_sound.pack(fill="x", padx=15, pady=5)

        f_sound_opts = tk.Frame(frame_sound)
        f_sound_opts.pack(fill="x")

        tk.Label(f_sound_opts, text="选择声音:", font=("Microsoft YaHei", 9)).pack(side="left")
        cb_sound = ttk.Combobox(
            f_sound_opts, textvariable=self.sound_choice_var, 
            values=["急促蜂鸣", "低沉提示", "三连警报", "系统响铃"], 
            state="readonly", width=10
        )
        cb_sound.pack(side="left", padx=5)

        chk_mute = tk.Checkbutton(
            f_sound_opts, text="🔇 静音模式", variable=self.mute_var,
            font=("Microsoft YaHei", 9, "bold"), fg="#D9534F"
        )
        chk_mute.pack(side="right")

        # 4. 运行控制与结果面板
        frame_run = tk.LabelFrame(self.root, text=" 4. 监控状态与统计 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=8)
        frame_run.pack(fill="x", padx=15, pady=5)

        self.btn_toggle_monitor = tk.Button(
            frame_run, text="▶ 开始自动监控", command=self.toggle_monitoring,
            font=("Microsoft YaHei", 11, "bold"), bg="#28A745", fg="white", relief="flat", cursor="hand2", height=2
        )
        self.btn_toggle_monitor.pack(fill="x", pady=5)

        f_res = tk.Frame(frame_run)
        f_res.pack(fill="x", pady=3)
        tk.Label(f_res, text="检测到的数字: ", font=("Microsoft YaHei", 9)).pack(side="left")
        self.lbl_current_res = tk.Label(f_res, text="---", font=("Microsoft YaHei", 10, "bold"), fg="#333333", wraplength=280, justify="left")
        self.lbl_current_res.pack(side="left", fill="x", expand=True)

        f_count = tk.Frame(frame_run)
        f_count.pack(fill="x", pady=5)
        tk.Label(f_count, text="报警累计: ", font=("Microsoft YaHei", 10)).pack(side="left")
        self.lbl_alarm_count = tk.Label(f_count, text="0 次", font=("Microsoft YaHei", 11, "bold"), fg="#D9534F")
        self.lbl_alarm_count.pack(side="left")

        btn_reset = tk.Button(f_count, text="清零", command=self.reset_count, font=("Microsoft YaHei", 8), relief="groove")
        btn_reset.pack(side="right")

    # ================= 框选逻辑 =================
    def start_selection(self):
        if self.is_monitoring:
            messagebox.showwarning("提示", "请先停止监控再重新框选区域！")
            return

        self.root.withdraw()
        self.overlay = tk.Toplevel(self.root)
        self.overlay.attributes("-fullscreen", True)
        self.overlay.attributes("-topmost", True)
        self.overlay.attributes("-alpha", 0.3)
        self.overlay.config(cursor="cross")

        self.canvas = tk.Canvas(self.overlay, cursor="cross", bg="gray")
        self.canvas.pack(fill="both", expand=True)

        self.canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.canvas.bind("<B1-Motion>", self.on_move_press)
        self.canvas.bind("<ButtonRelease-1>", self.on_button_release)

    def on_button_press(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, 1, 1, outline='red', width=2)

    def on_move_press(self, event):
        self.canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)

    def on_button_release(self, event):
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)

        self.overlay.destroy()
        self.root.deiconify()

        if (x2 - x1) > 5 and (y2 - y1) > 5:
            self.bbox = (x1, y1, x2, y2)
            self.lbl_area_status.config(
                text=f"已选择区域: ({x1},{y1}) -> ({x2},{y2}) [{x2-x1}x{y2-y1}]", 
                fg="#008000"
            )
            self.single_recognize()

    # ================= 声音播放逻辑 =================
    def play_alarm_sound(self):
        if self.mute_var.get():
            return

        sound_type = self.sound_choice_var.get()

        def _sound_thread():
            try:
                if sound_type == "急促蜂鸣":
                    winsound.Beep(2000, 120)
                    time.sleep(0.05)
                    winsound.Beep(2000, 120)
                elif sound_type == "低沉提示":
                    winsound.Beep(800, 300)
                elif sound_type == "三连警报":
                    winsound.Beep(1200, 100)
                    winsound.Beep(1600, 100)
                    winsound.Beep(2000, 100)
                elif sound_type == "系统响铃":
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            except Exception:
                pass

        threading.Thread(target=_sound_thread, daemon=True).start()

    # ================= 智能切块多数字识别算法 =================
    def ocr_process_multi(self, img):
        """支持大表格、多数字切片的增强识别算法"""
        try:
            # 1. 2倍放大提升小文字清晰度
            w, h = img.size
            img_resized = img.resize((w * 2, h * 2))

            img_byte_arr = io.BytesIO()
            img_resized.save(img_byte_arr, format='PNG')
            image_bytes = img_byte_arr.getvalue()

            results = []

            # 2. 智能检测区域内的每一个文本块坐标
            bboxes = self.det.detection(image_bytes)

            if bboxes:
                # 针对切出的每一个数字小块单独识别
                for bbox in bboxes:
                    x1, y1, x2, y2 = bbox
                    margin = 4  # 边缘微扩展
                    crop_box = (
                        max(0, x1 - margin),
                        max(0, y1 - margin),
                        min(img_resized.width, x2 + margin),
                        min(img_resized.height, y2 + margin)
                    )
                    cropped = img_resized.crop(crop_box)

                    c_bytes = io.BytesIO()
                    cropped.save(c_bytes, format='PNG')

                    raw_txt = self.ocr.classification(c_bytes.getvalue())
                    digits = "".join(re.findall(r'[\d\.]+', raw_txt))
                    if digits and digits not in results:
                        results.append(digits)

            # 3. 如果没检测出单独小块，备用方案：对整体识别
            if not results:
                raw_text = self.ocr.classification(image_bytes)
                digits = "".join(re.findall(r'[\d\.]+', raw_text))
                if digits:
                    results.append(digits)

            return results  # 返回列表，如 ['10.5', '88', '100']

        except Exception:
            return []

    def single_recognize(self):
        """单次预览"""
        if not self.bbox:
            return
        img = ImageGrab.grab(bbox=self.bbox)
        nums = self.ocr_process_multi(img)
        self.lbl_current_res.config(text=", ".join(nums) if nums else "未检测到数字", fg="#333333")

    def toggle_monitoring(self):
        if not self.is_monitoring:
            if not self.bbox:
                messagebox.showwarning("警告", "请先点击【框选/重选表格区域】选择监控区域！")
                return

            self.is_monitoring = True
            self.btn_toggle_monitor.config(text="⏹ 停止监控", bg="#DC3545")
            self.btn_select.config(state="disabled")

            threading.Thread(target=self.monitor_loop, daemon=True).start()
        else:
            self.stop_monitoring()

    def stop_monitoring(self):
        self.is_monitoring = False
        self.btn_toggle_monitor.config(text="▶ 开始自动监控", bg="#28A745")
        self.btn_select.config(state="normal")

    def monitor_loop(self):
        """后台持续监控核心逻辑"""
        while self.is_monitoring:
            if not self.bbox:
                break

            img = ImageGrab.grab(bbox=self.bbox)
            detected_numbers = self.ocr_process_multi(img)

            raw_targets = self.target_nums_var.get().replace('，', ',').split(',')
            target_list = [t.strip() for t in raw_targets if t.strip()]

            # 匹配逻辑：检查所有切片识别出的数字中，是否有包含目标的数字
            is_triggered = False
            matched_items = []

            if detected_numbers:
                if not target_list:
                    is_triggered = True
                else:
                    for target in target_list:
                        for num_str in detected_numbers:
                            if target == num_str or target in num_str:
                                is_triggered = True
                                matched_items.append(num_str)
                                break

            # 线程安全更新界面
            self.root.after(0, self.update_ui_result, detected_numbers, is_triggered)

            # 间隔休眠
            try:
                interval = float(self.interval_var.get())
                if interval < 0.2:
                    interval = 0.2
            except ValueError:
                interval = 2.0

            steps = int(interval / 0.1)
            for _ in range(max(1, steps)):
                if not self.is_monitoring:
                    break
                time.sleep(0.1)

    def update_ui_result(self, detected_numbers, triggered):
        """UI 主线程响应结果"""
        if detected_numbers:
            display_str = ", ".join(detected_numbers)
            self.lbl_current_res.config(text=display_str, fg="#008000" if triggered else "#333333")
            pyperclip.copy(display_str)
        else:
            self.lbl_current_res.config(text="未识别到数字", fg="#999999")

        if triggered:
            self.alarm_count += 1
            self.lbl_alarm_count.config(text=f"{self.alarm_count} 次")
            self.play_alarm_sound()

    def reset_count(self):
        self.alarm_count = 0
        self.lbl_alarm_count.config(text="0 次")

    def on_closing(self):
        self.is_monitoring = False
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenOCRApp(root)
    root.mainloop()
