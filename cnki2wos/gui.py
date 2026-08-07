"""Tkinter interface for CNKI2WOS."""

from __future__ import annotations

from pathlib import Path
from queue import Empty, SimpleQueue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from . import __version__
from .core import ConversionResult, convert_file


class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"CNKI2WOS {__version__}")
        self.root.geometry("720x480")
        self.root.minsize(680, 440)

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.status = tk.StringVar(value="请选择 CNKI 导出的 RefWorks 文本文件。")
        self.events: SimpleQueue[tuple[str, object]] = SimpleQueue()

        self._create_widgets()
        self.root.after(100, self._poll_events)

    def _create_widgets(self) -> None:
        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)

        title = ttk.Label(main, text="CNKI 文献数据转 WOS 标记文本", font=("Microsoft YaHei UI", 16, "bold"))
        title.pack(anchor="w", pady=(0, 4))
        ttk.Label(main, text="支持 UTF-8、UTF-8 BOM 和 GB18030；输出统一为 UTF-8。").pack(anchor="w", pady=(0, 14))

        input_frame = ttk.LabelFrame(main, text="1. 选择输入文件", padding=10)
        input_frame.pack(fill="x", pady=(0, 10))
        ttk.Entry(input_frame, textvariable=self.input_path, state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(input_frame, text="浏览…", command=self.select_input).pack(side="right")

        output_frame = ttk.LabelFrame(main, text="2. 设置输出文件", padding=10)
        output_frame.pack(fill="x", pady=(0, 10))
        ttk.Entry(output_frame, textvariable=self.output_path, state="readonly").pack(side="left", fill="x", expand=True, padx=(0, 8))
        ttk.Button(output_frame, text="另存为…", command=self.select_output).pack(side="right")

        self.convert_button = ttk.Button(main, text="开始转换", command=self.start_conversion)
        self.convert_button.pack(fill="x", ipady=8, pady=(0, 10))

        log_frame = ttk.LabelFrame(main, text="运行日志", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=5, state="disabled", wrap="word", font=("Consolas", 10))
        self.log_area.pack(fill="both", expand=True)

        ttk.Label(main, textvariable=self.status).pack(anchor="w", pady=(8, 0))

    def _log(self, message: str) -> None:
        self.log_area.configure(state="normal")
        self.log_area.insert("end", message + "\n")
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def select_input(self) -> None:
        selected = filedialog.askopenfilename(
            title="选择 CNKI RefWorks 文本",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if not selected:
            return
        self.input_path.set(selected)
        source = Path(selected)
        self.output_path.set(str(source.with_name(f"{source.stem}_wos.txt")))
        self._log(f"输入：{selected}")

    def select_output(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="保存 WOS 标记文本",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
        )
        if selected:
            self.output_path.set(selected)
            self._log(f"输出：{selected}")

    def start_conversion(self) -> None:
        input_file = self.input_path.get()
        output_file = self.output_path.get()
        if not input_file or not output_file:
            messagebox.showerror("缺少路径", "请先选择输入文件和输出文件。")
            return

        self.convert_button.configure(state="disabled", text="正在转换…")
        self.status.set("正在读取和转换记录…")
        self._log("开始转换。")
        threading.Thread(
            target=self._convert_worker,
            args=(input_file, output_file),
            daemon=True,
        ).start()

    def _convert_worker(self, input_file: str, output_file: str) -> None:
        try:
            result = convert_file(input_file, output_file)
            self.events.put(("success", (result, output_file)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "success":
                    result, output_file = payload
                    self._on_success(result, output_file)
                else:
                    self._on_error(str(payload))
        except Empty:
            pass
        self.root.after(100, self._poll_events)

    def _on_success(self, result: ConversionResult, output_file: str) -> None:
        self.convert_button.configure(state="normal", text="开始转换")
        self.status.set(f"完成：输出 {result.output_records} 条记录。")
        self._log(f"输入编码：{result.input_encoding}")
        self._log(f"输入 {result.input_records} 条，输出 {result.output_records} 条，跳过 {result.skipped_records} 条。")
        for warning in result.warnings:
            self._log(f"警告：{warning}")
        self._log(f"已保存：{output_file}")
        messagebox.showinfo("转换完成", f"成功输出 {result.output_records} 条记录。\n\n{output_file}")

    def _on_error(self, message: str) -> None:
        self.convert_button.configure(state="normal", text="开始转换")
        self.status.set("转换失败，请检查日志和输入文件。")
        self._log(f"错误：{message}")
        messagebox.showerror("转换失败", message)


def main() -> None:
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
