import io
import os
import re
import sys
import time
import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
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
        self.root.title("数字报警器 v4.0")
        self.root.geometry("460x680")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        # 核心状态变量
        self.bbox = None                    # 框选区域 (x1, y1, x2, y2)
        self.is_monitoring = False          # 监控状态
        self.alarm_count = 0                # 报警累计次数
        self.last_matched_targets = set()   # 上一次匹配到的目标集合（去重核心）
        self.is_alarm_ringing = False       # 是否正在持续报警响铃
        self.is_log_expanded = True         # 日志展开状态

        # UI 绑定变量
        self.target_nums_var = tk.StringVar(value="20, 88")   # 默认目标数字
        self.interval_var = tk.StringVar(value="2.0")         # 默认监控间隔(秒)
        self.sound_choice_var = tk.StringVar(value="急促高音")   # 默认声音
        self.mute_var = tk.BooleanVar(value=False)            # 静音状态

        # 初始化 ddddocr 识别引擎
        try:
            self.ocr = ddddocr.DdddOcr(show_ad=False)
            self.det = ddddocr.DdddOcr(det=True, show_ad=False)
        except Exception as e:
            messagebox.showerror("初始化错误", f"OCR引擎加载失败: {e}")

        # 加载窗口图标
        ico_file = resource_path("1.ico")
        if os.path.exists(ico_file):
            try:
                self.root.iconbitmap(ico_file)
            except Exception:
                pass

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.create_widgets()
        self.add_log("系统初始化完成，等待配置。")

    def create_widgets(self):
        # 1. 区域框选模块
        frame_area = tk.LabelFrame(self.root, text=" 1. 监控区域设置 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=6)
        frame_area.pack(fill="x", padx=12, pady=4)

        self.btn_select = tk.Button(
            frame_area, text="🔍 框选/重选表格区域", command=self.start_selection,
            font=("Microsoft YaHei", 10, "bold"), bg="#007ACC", fg="white", relief="flat", cursor="hand2"
        )
        self.btn_select.pack(fill="x", pady=2)

        self.lbl_area_status = tk.Label(frame_area, text="当前未选择区域", font=("Microsoft YaHei", 9), fg="#888888")
        self.lbl_area_status.pack(pady=2)

        # 2. 规则与参数设置模块
        frame_rules = tk.LabelFrame(self.root, text=" 2. 报警规则与间隔 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=6)
        frame_rules.pack(fill="x", padx=12, pady=4)

        f_target = tk.Frame(frame_rules)
        f_target.pack(fill="x", pady=2)
        tk.Label(f_target, text="目标数字:", font=("Microsoft YaHei", 9), width=10, anchor="w").pack(side="left")
        entry_target = tk.Entry(f_target, textvariable=self.target_nums_var, font=("Microsoft YaHei", 9))
        entry_target.pack(side="left", fill="x", expand=True)
        tk.Label(f_target, text=" (逗号隔开)", font=("Microsoft YaHei", 8), fg="#888888").pack(side="left")

        f_interval = tk.Frame(frame_rules)
        f_interval.pack(fill="x", pady=2)
        tk.Label(f_interval, text="监控间隔(秒):", font=("Microsoft YaHei", 9), width=10, anchor="w").pack(side="left")
        entry_interval = tk.Entry(f_interval, textvariable=self.interval_var, font=("Microsoft YaHei", 9), width=10)
        entry_interval.pack(side="left")

        # 3. 声音与消除报警模块
        frame_sound = tk.LabelFrame(self.root, text=" 3. 报警声音与控制 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=6)
        frame_sound.pack(fill="x", padx=12, pady=4)

        f_sound_opts = tk.Frame(frame_sound)
        f_sound_opts.pack(fill="x", pady=2)

        tk.Label(f_sound_opts, text="选择音效:", font=("Microsoft YaHei", 9)).pack(side="left")
        cb_sound = ttk.Combobox(
            f_sound_opts, textvariable=self.sound_choice_var, 
            values=["急促高音", "防空警报", "救护车警笛", "柔和双音", "系统错误音", "系统警告音", "系统提示音"], 
            state="readonly", width=12
        )
        cb_sound.pack(side="left", padx=5)

        chk_mute = tk.Checkbutton(
            f_sound_opts, text="🔇 静音", variable=self.mute_var, command=self.on_mute_toggled,
            font=("Microsoft YaHei", 9, "bold"), fg="#D9534F"
        )
        chk_mute.pack(side="right")

        self.btn_stop_alarm = tk.Button(
            frame_sound, text="🔕 消除报警 (停止响铃)", command=self.stop_alarm_loop,
            font=("Microsoft YaHei", 10, "bold"), bg="#E0E0E0", fg="#666666", state="disabled", relief="flat", cursor="hand2"
        )
        self.btn_stop_alarm.pack(fill="x", pady=4)

        # 4. 监控状态与统计模块
        frame_run = tk.LabelFrame(self.root, text=" 4. 监控状态与统计 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=6)
        frame_run.pack(fill="x", padx=12, pady=4)

        self.btn_toggle_monitor = tk.Button(
            frame_run, text="▶ 开始自动监控", command=self.toggle_monitoring,
            font=("Microsoft YaHei", 11, "bold"), bg="#28A745", fg="white", relief="flat", cursor="hand2", height=2
        )
        self.btn_toggle_monitor.pack(fill="x", pady=4)

        f_res = tk.Frame(frame_run)
        f_res.pack(fill="x", pady=2)
        tk.Label(f_res, text="当前检测: ", font=("Microsoft YaHei", 9)).pack(side="left")
        self.lbl_current_res = tk.Label(f_res, text="---", font=("Microsoft YaHei", 10, "bold"), fg="#333333", wraplength=300, justify="left")
        self.lbl_current_res.pack(side="left", fill="x", expand=True)

        f_count = tk.Frame(frame_run)
        f_count.pack(fill="x", pady=2)
        tk.Label(f_count, text="报警次数: ", font=("Microsoft YaHei", 9)).pack(side="left")
        self.lbl_alarm_count = tk.Label(f_count, text="0 次", font=("Microsoft YaHei", 11, "bold"), fg="#D9534F")
        self.lbl_alarm_count.pack(side="left")

        btn_reset = tk.Button(f_count, text="清零", command=self.reset_count, font=("Microsoft YaHei", 8), relief="groove")
        btn_reset.pack(side="right")

        # 5. 可收起的日志面板
        self.frame_log = tk.LabelFrame(self.root, text=" 5. 运行与报警日志 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=4)
        self.frame_log.pack(fill="both", expand=True, padx=12, pady=4)

        f_log_head = tk.Frame(self.frame_log)
        f_log_head.pack(fill="x")

        self.btn_toggle_log = tk.Button(
            f_log_head, text="▲ 收起日志", command=self.toggle_log_panel,
            font=("Microsoft YaHei", 8), relief="groove"
        )
        self.btn_toggle_log.pack(side="right", pady=2)

        self.log_content_frame = tk.Frame(self.frame_log)
        self.log_content_frame.pack(fill="both", expand=True)

        self.log_text = scrolledtext.ScrolledText(self.log_content_frame, height=6, font=("Consolas", 8))
        self.log_text.pack(fill="both", expand=True, pady=2)

    # ================= 日志记录与折叠 =================
    def add_log(self, message):
        """格式化添加一条日志"""
        now = datetime.datetime.now().strftime("%H:%M:%S")
        log_str = f"[{now}] {message}\n"
        self.log_text.insert(tk.END, log_str)
        self.log_text.see(tk.END)

    def toggle_log_panel(self):
        """切换日志展开/收起"""
        if self.is_log_expanded:
            self.log_content_frame.pack_forget()
            self.btn_toggle_log.config(text="▼ 展开日志")
            self.is_log_expanded = False
            self.root.geometry("460x520")  # 缩小窗口
        else:
            self.log_content_frame.pack(fill="both", expand=True)
            self.btn_toggle_log.config(text="▲ 收起日志")
            self.is_log_expanded = True
            self.root.geometry("460x680")  # 展开窗口

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
                text=f"已选区域: ({x1},{y1}) -> ({x2},{y2}) [{x2-x1}x{y2-y1}]", 
                fg="#008000"
            )
            self.add_log(f"修改监控区域: ({x1},{y1}) 到 ({x2},{y2})")
            self.single_recognize()

    # ================= 持续循环报警音效逻辑 =================
    def start_alarm_loop(self):
        """触发持续报警"""
        if self.mute_var.get():
            return

        if not self.is_alarm_ringing:
            self.is_alarm_ringing = True
            # 高亮红闪消音按钮
            self.btn_stop_alarm.config(bg="#DC3545", fg="white", state="normal")
            threading.Thread(target=self._alarm_sound_worker, daemon=True).start()

    def stop_alarm_loop(self):
        """消除/停止报警声音"""
        self.is_alarm_ringing = False
        self.btn_stop_alarm.config(bg="#E0E0E0", fg="#666666", state="disabled")

    def on_mute_toggled(self):
        if self.mute_var.get():
            self.stop_alarm_loop()

    def _alarm_sound_worker(self):
        """后台持续响铃线程"""
        while self.is_alarm_ringing and not self.mute_var.get():
            sound_type = self.sound_choice_var.get()
            try:
                if sound_type == "急促高音":
                    winsound.Beep(2500, 150)
                    time.sleep(0.1)
                elif sound_type == "防空警报":
                    for freq in range(600, 1200, 100):
                        if not self.is_alarm_ringing or self.mute_var.get(): break
                        winsound.Beep(freq, 35)
                    for freq in range(1200, 600, -100):
                        if not self.is_alarm_ringing or self.mute_var.get(): break
                        winsound.Beep(freq, 35)
                elif sound_type == "救护车警笛":
                    winsound.Beep(900, 250)
                    time.sleep(0.05)
                    winsound.Beep(600, 250)
                    time.sleep(0.05)
                elif sound_type == "柔和双音":
                    winsound.Beep(800, 150)
                    winsound.Beep(1000, 150)
                    time.sleep(0.3)
                elif sound_type == "系统错误音":
                    winsound.MessageBeep(winsound.MB_ICONHAND)
                    time.sleep(0.4)
                elif sound_type == "系统警告音":
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    time.sleep(0.4)
                elif sound_type == "系统提示音":
                    winsound.MessageBeep(winsound.MB_ICONASTERISK)
                    time.sleep(0.4)
            except Exception:
                pass
            time.sleep(0.1)
        self.stop_alarm_loop()

    # ================= OCR识别核心 =================
    def ocr_process_multi(self, img):
        """2倍放大切片识别"""
        try:
            w, h = img.size
            img_resized = img.resize((w * 2, h * 2))

            img_byte_arr = io.BytesIO()
            img_resized.save(img_byte_arr, format='PNG')
            image_bytes = img_byte_arr.getvalue()

            results = []
            bboxes = self.det.detection(image_bytes)

            if bboxes:
                for bbox in bboxes:
                    x1, y1, x2, y2 = bbox
                    margin = 4
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

            if not results:
                raw_text = self.ocr.classification(image_bytes)
                digits = "".join(re.findall(r'[\d\.]+', raw_text))
                if digits:
                    results.append(digits)

            return results
        except Exception:
            return []

    def single_recognize(self):
        if not self.bbox:
            return
        img = ImageGrab.grab(bbox=self.bbox)
        nums = self.ocr_process_multi(img)
        res_str = ", ".join(nums) if nums else "未检测到数字"
        self.lbl_current_res.config(text=res_str, fg="#333333")

    def toggle_monitoring(self):
        if not self.is_monitoring:
            if not self.bbox:
                messagebox.showwarning("警告", "请先点击【框选/重选表格区域】选择监控区域！")
                return

            self.is_monitoring = True
            self.last_matched_targets = set() # 启动时重置匹配状态
            self.btn_toggle_monitor.config(text="⏹ 停止监控", bg="#DC3545")
            self.btn_select.config(state="disabled")

            self.add_log("▶ 开始自动监控...")
            threading.Thread(target=self.monitor_loop, daemon=True).start()
        else:
            self.stop_monitoring()

    def stop_monitoring(self):
        self.is_monitoring = False
        self.stop_alarm_loop()
        self.btn_toggle_monitor.config(text="▶ 开始自动监控", bg="#28A745")
        self.btn_select.config(state="normal")
        self.add_log("⏹ 已停止监控。")

    # ================= 监控主循环与变动去重逻辑 =================
    def monitor_loop(self):
        """后台轮询监控逻辑"""
        while self.is_monitoring:
            if not self.bbox:
                break

            img = ImageGrab.grab(bbox=self.bbox)
            detected_numbers = self.ocr_process_multi(img)

            raw_targets = self.target_nums_var.get().replace('，', ',').split(',')
            target_list = [t.strip() for t in raw_targets if t.strip()]

            # 计算本次匹配到的目标集合
            current_matched = set()
            if detected_numbers:
                if not target_list:
                    current_matched = set(detected_numbers)
                else:
                    for target in target_list:
                        for num_str in detected_numbers:
                            if target == num_str or target in num_str:
                                current_matched.add(target)

            # 去重核心判断：对比上一次匹配结果
            is_new_trigger = False
            if current_matched:
                if current_matched != self.last_matched_targets:
                    # 发现新目标出现（或目标集合发生变化），判定为一次新报警事件
                    is_new_trigger = True
                    self.last_matched_targets = current_matched
            else:
                # 区域内目标数字消失，重置状态
                self.last_matched_targets = set()

            # 刷新 UI 与处理报警
            self.root.after(0, self.update_ui_result, detected_numbers, current_matched, is_new_trigger)

            # 轮询休眠
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

    def update_ui_result(self, detected_numbers, current_matched, is_new_trigger):
        """UI 刷新与变动触发报警"""
        if detected_numbers:
            display_str = ", ".join(detected_numbers)
            self.lbl_current_res.config(
                text=display_str, 
                fg="#008000" if current_matched else "#333333"
            )
            pyperclip.copy(display_str)
        else:
            self.lbl_current_res.config(text="未识别到数字", fg="#999999")

        # 只有在产生新报警事件时才增加计数并启动持续响铃
        if is_new_trigger:
            self.alarm_count += 1
            self.lbl_alarm_count.config(text=f"{self.alarm_count} 次")

            matched_str = ", ".join(list(current_matched))
            self.add_log(f"🚨 触发报警第 {self.alarm_count} 次！检测到目标数字: [{matched_str}]")

            # 开启持续循环报警
            self.start_alarm_loop()

    def reset_count(self):
        """清零计数与状态"""
        self.alarm_count = 0
        self.last_matched_targets = set()
        self.lbl_alarm_count.config(text="0 次")
        self.add_log("报警计数已清零。")

    def on_closing(self):
        """关闭程序清理"""
        self.is_monitoring = False
        self.stop_alarm_loop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenOCRApp(root)
    root.mainloop()
