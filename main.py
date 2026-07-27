import os
import sys
import tkinter as tk
from tkinter import messagebox
from PIL import ImageGrab
import pytesseract
import pyperclip

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

# ==================== 资源路径兼容 (PyInstaller 单文件模式) ====================
def resource_path(relative_path):
    """ 获取静态资源或打包后临时解压文件的绝对路径 """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)

# 1. 优先调用内嵌打包的 Tesseract 引擎
bundled_tesseract = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))
if os.path.exists(bundled_tesseract):
    pytesseract.pytesseract.tesseract_cmd = bundled_tesseract
else:
    # 2. 本地开发测试回退路径
    default_win_path = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if os.path.exists(default_win_path):
        pytesseract.pytesseract.tesseract_cmd = default_win_path


class ScreenOCRApp:
    def __init__(self, root):
        self.root = root
        self.root.title("数字报警")
        self.root.geometry("360x220")
        self.root.attributes("-topmost", True)  # 保持最前
        self.root.resizable(False, False)

        # 设置软件窗口图标 (1.ico)
        ico_file = resource_path("1.ico")
        if os.path.exists(ico_file):
            try:
                self.root.iconbitmap(ico_file)
            except Exception:
                pass

        # UI 界面
        self.btn_select = tk.Button(
            root, 
            text="🔍 点击框选识别", 
            command=self.start_selection, 
            font=("Microsoft YaHei", 12, "bold"), 
            bg="#007ACC", 
            fg="white", 
            height=2,
            relief="flat",
            cursor="hand2"
        )
        self.btn_select.pack(pady=20, padx=20, fill='x')

        self.label_title = tk.Label(root, text="识别结果：", font=("Microsoft YaHei", 10), fg="#666666")
        self.label_title.pack()

        self.label_result = tk.Label(root, text="等待识别...", font=("Microsoft YaHei", 14, "bold"), fg="#333333")
        self.label_result.pack(pady=5)

        self.label_tip = tk.Label(root, text="（结果已自动复制到剪贴板）", font=("Microsoft YaHei", 8), fg="#999999")
        self.label_tip.pack()

    def start_selection(self):
        """隐藏主窗口，开启全屏框选"""
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

        self.start_x = None
        self.start_y = None
        self.rect = None

    def on_button_press(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.rect = self.canvas.create_rectangle(
            self.start_x, self.start_y, 1, 1, outline='red', width=2
        )

    def on_move_press(self, event):
        cur_x, cur_y = (event.x, event.y)
        self.canvas.coords(self.rect, self.start_x, self.start_y, cur_x, cur_y)

    def on_button_release(self, event):
        end_x, end_y = (event.x, event.y)

        x1 = min(self.start_x, end_x)
        y1 = min(self.start_y, end_y)
        x2 = max(self.start_x, end_x)
        y2 = max(self.start_y, end_y)

        self.overlay.destroy()
        self.root.deiconify()

        if (x2 - x1) > 5 and (y2 - y1) > 5:
            img = ImageGrab.grab(bbox=(x1, y1, x2, y2))
            self.recognize_digits(img)

    def recognize_digits(self, img):
        """纯数字/小数点识别逻辑"""
        try:
            custom_config = r'--psm 6 -c tessedit_char_whitelist=0123456789.'
            text = pytesseract.image_to_string(img, config=custom_config).strip()

            if text:
                self.label_result.config(text=text, fg="#008000")
                pyperclip.copy(text)
            else:
                self.label_result.config(text="未识别到数字", fg="#FF0000")

        except Exception as e:
            self.label_result.config(text="识别失败", fg="#FF0000")
            messagebox.showerror("识别错误", f"请检查环境或框选区域。\n\n详情:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = ScreenOCRApp(root)
    root.mainloop()