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
        self.root.title("数字报警器 v2.0")
        self.root.geometry("420x530")
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

        # 初始化 ddddocr 引擎
        try:
            self.ocr = ddddocr.DdddOcr(show_ad=False)
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
            frame_area, text="🔍 框选/重选表格区域", command=self.start_selection,
            font=("Microsoft YaHei", 10, "bold"), bg="#007ACC", fg="white", relief="flat", cursor="hand2"
        )
        self.btn_select.pack(fill="x", pady=2)

        self.lbl_area_status = tk.Label(frame_area, text="当前未选择区域", font=("Microsoft YaHei", 9), fg="#888888")
        self.lbl_area_status.pack(pady=2)

        # 2. 规则与参数设置模块
        frame_rules = tk.LabelFrame(self.root, text=" 2. 报警规则与间隔 ", font=("Microsoft YaHei", 9, "bold"), padx=10, pady=8)
        frame_rules.pack(fill="x", padx=15, pady=5)

        # 目标数字
        f_target = tk.Frame(frame_rules)
        f_target.pack(fill="x", pady=3)
        tk.Label(f_target, text="目标数字:", font=("Microsoft YaHei", 9), width=10, anchor="w").pack(side="left")
        entry_target = tk.Entry(f_target, textvariable=self.target_nums_var, font=("Microsoft YaHei", 9))
        entry_target.pack(side="left", fill="x", expand=True)
        tk.Label(f_target, text=" (逗号隔开)", font=("Microsoft YaHei", 8), fg="#888888").pack(side="left")

        # 识别间隔
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

        # 识别结果与统计
        f_res = tk.Frame(frame_run)
        f_res.pack(fill="x", pady=3)
        tk.Label(f_res, text="实时识别: ", font=("Microsoft YaHei", 10)).pack(side="left")
        self.lbl_current_res = tk.Label(f_res, text="---", font=("Microsoft YaHei", 11, "bold"), fg="#333333")
        self.lbl_current_res.pack(side="left")

        f_count = tk.Frame(frame_run)
        f_count.pack(fill="x", pady=3)
        tk.Label(f_count, text="报警累计: ", font=("Microsoft YaHei", 10)).pack(side="left")
        self.lbl_alarm_count = tk.Label(f_count, text="0 次", font=("Microsoft YaHei", 11, "bold"), fg="#D9534F")
        self.lbl_alarm_count.pack(side="left")

        btn_reset = tk.Button(f_count, text="清零", command=self.reset_count, font=("Microsoft YaHei", 8), relief="groove")
        btn_reset.pack(side="right")

    # ================= 框选截图逻辑 =================
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
            # 立即进行一次预览识别
            self.single_recognize()

    # ================= 声音播放逻辑 =================
    def play_alarm_sound(self):
        """如果在静音状态下则跳过，否则异步播放选中声音"""
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

    # ================= 识别与监控循环 =================
    def single_recognize(self):
        """单次识别预览"""
        if not self.bbox:
            return
        img = ImageGrab.grab(bbox=self.bbox)
        text = self.ocr_process(img)
        self.lbl_current_res.config(text=text if text else "未检测到数字", fg="#333333")

    def ocr_process(self, img):
        """通过内存处理截图并提炼数字"""
        try:
            img_byte_arr = io.BytesIO()
            img.save(img_byte_arr, format='PNG')
            raw_text = self.ocr.classification(img_byte_arr.getvalue())
            return "".join(re.findall(r'[\d\.]+', raw_text))
        except Exception:
            return ""

    def toggle_monitoring(self):
        """开启或停止监控"""
        if not self.is_monitoring:
            if not self.bbox:
                messagebox.showwarning("警告", "请先点击【框选/重选表格区域】选择监控区域！")
                return

            self.is_monitoring = True
            self.btn_toggle_monitor.config(text="⏹ 停止监控", bg="#DC3545")
            self.btn_select.config(state="disabled")

            # 启动后台独立线程处理监控循环，防止主界面卡顿
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

            # 1. 截图与识别
            img = ImageGrab.grab(bbox=self.bbox)
            recognized_text = self.ocr_process(img)

            # 2. 解析目标数字列表
            raw_targets = self.target_nums_var.get().replace('，', ',').split(',')
            target_list = [t.strip() for t in raw_targets if t.strip()]

            # 3. 检查匹配逻辑
            is_triggered = False
            if recognized_text:
                if not target_list:
                    # 如果未设置目标数字，只要区域内有任何数字就触发
                    is_triggered = True
                else:
                    for target in target_list:
                        if target in recognized_text:
                            is_triggered = True
                            break

            # 4. 线程安全更新 UI
            self.root.after(0, self.update_ui_result, recognized_text, is_triggered)

            # 5. 解析休眠间隔
            try:
                interval = float(self.interval_var.get())
                if interval < 0.2:
                    interval = 0.2
            except ValueError:
                interval = 2.0

            # 分拆休眠，使用户点击“停止”时能瞬间响应
            steps = int(interval / 0.1)
            for _ in range(max(1, steps)):
                if not self.is_monitoring:
                    break
                time.sleep(0.1)

    def update_ui_result(self, text, triggered):
        """UI 主线程响应结果与报警"""
        if text:
            self.lbl_current_res.config(text=text, fg="#008000" if triggered else "#333333")
            pyperclip.copy(text)
        else:
            self.lbl_current_res.config(text="未识别到数字", fg="#999999")

        # 若命中目标数字，触发计数与声音
        if triggered:
            self.alarm_count += 1
            self.lbl_alarm_count.config(text=f"{self.alarm_count} 次")
            self.play_alarm_sound()

    def reset_count(self):
        """清零报警次数"""
        self.alarm_count = 0
        self.lbl_alarm_count.config(text="0 次")

    def on_closing(self):
        """关闭窗口时退出监控"""
        self.is_monitoring = False
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenOCRApp(root)
    root.mainloop()
