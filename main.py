import os
import sys
import subprocess
import threading
import queue
import shutil
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    Root = TkinterDnD.Tk
except ImportError:
    DND_FILES = None
    Root = tk.Tk

BASE = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
ICON = BASE / 'app.ico'

def ffmpeg_path():
    bundled = BASE / 'ffmpeg.exe'
    return str(bundled) if bundled.is_file() else shutil.which('ffmpeg')

class App:
    def __init__(self, root):
        self.root = root
        self.root.title('MP3 → WAV 一括変換')
        self.root.geometry('760x540')
        self.root.minsize(600, 450)
        if ICON.exists():
            try: root.iconbitmap(str(ICON))
            except tk.TclError: pass
        self.files = []
        self.events = queue.Queue()
        self.running = False
        self.output_dir = tk.StringVar(value=str(Path.home() / 'Music'))
        self.sample_rate = tk.StringVar(value='元のまま')
        self.bit_depth = tk.StringVar(value='16bit')
        self.status = tk.StringVar(value='MP3ファイルを追加してください。')
        outer = ttk.Frame(root, padding=16)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='MP3 → WAV 一括変換', font=('Yu Gothic UI', 17, 'bold')).pack(anchor='w')
        ttk.Label(outer, text='複数のMP3を追加し、まとめてWAVに変換できます。').pack(anchor='w', pady=(3, 12))
        file_frame = ttk.LabelFrame(outer, text='変換するファイル', padding=8)
        file_frame.pack(fill='both', expand=True)
        self.listbox = tk.Listbox(file_frame, selectmode='extended', height=9)
        scroll = ttk.Scrollbar(file_frame, orient='vertical', command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scroll.set)
        self.listbox.pack(side='left', fill='both', expand=True)
        scroll.pack(side='right', fill='y')
        if DND_FILES:
            self.listbox.drop_target_register(DND_FILES)
            self.listbox.dnd_bind('<<Drop>>', lambda e: self.add_files(self.root.tk.splitlist(e.data)))
        actions = ttk.Frame(outer)
        actions.pack(fill='x', pady=(8, 10))
        self.add_btn = ttk.Button(actions, text='MP3を追加', command=self.pick_files)
        self.add_btn.pack(side='left')
        self.remove_btn = ttk.Button(actions, text='選択を削除', command=self.remove_selected)
        self.remove_btn.pack(side='left', padx=8)
        self.clear_btn = ttk.Button(actions, text='すべて削除', command=self.clear)
        self.clear_btn.pack(side='left')
        out = ttk.LabelFrame(outer, text='出力先', padding=8)
        out.pack(fill='x')
        ttk.Entry(out, textvariable=self.output_dir).pack(side='left', fill='x', expand=True)
        self.browse_btn = ttk.Button(out, text='参照', command=self.pick_output)
        self.browse_btn.pack(side='left', padx=(8, 0))
        settings = ttk.Frame(outer)
        settings.pack(fill='x', pady=12)
        ttk.Label(settings, text='ビット深度').pack(side='left')
        self.depth_combo = ttk.Combobox(settings, textvariable=self.bit_depth, values=['16bit', '24bit'], state='readonly', width=10)
        self.depth_combo.pack(side='left', padx=(8, 24))
        ttk.Label(settings, text='サンプルレート').pack(side='left')
        self.rate_combo = ttk.Combobox(settings, textvariable=self.sample_rate, values=['元のまま', '44100', '48000', '96000'], state='readonly', width=12)
        self.rate_combo.pack(side='left', padx=8)
        self.progress = ttk.Progressbar(outer, mode='determinate')
        self.progress.pack(fill='x')
        ttk.Label(outer, textvariable=self.status).pack(anchor='w', pady=(5, 8))
        self.convert_btn = ttk.Button(outer, text='一括変換を開始', command=self.start)
        self.convert_btn.pack(fill='x', ipady=5)
        self.root.after(100, self.poll)

    def pick_files(self):
        paths = filedialog.askopenfilenames(title='MP3ファイルを選択', filetypes=[('MP3', '*.mp3')])
        self.add_files(paths)

    def add_files(self, paths):
        known = {os.path.normcase(os.path.abspath(p)) for p in self.files}
        for p in paths:
            p = str(Path(p))
            key = os.path.normcase(os.path.abspath(p))
            if p.lower().endswith('.mp3') and Path(p).is_file() and key not in known:
                self.files.append(p)
                self.listbox.insert('end', p)
                known.add(key)
        self.status.set(f'{len(self.files)} ファイルを登録しました。')

    def remove_selected(self):
        for i in reversed(self.listbox.curselection()):
            del self.files[i]
            self.listbox.delete(i)
        self.status.set(f'{len(self.files)} ファイルを登録しました。')

    def clear(self):
        self.files.clear()
        self.listbox.delete(0, 'end')
        self.status.set('MP3ファイルを追加してください。')

    def pick_output(self):
        folder = filedialog.askdirectory(title='WAVの出力先を選択')
        if folder: self.output_dir.set(folder)

    def start(self):
        if self.running: return
        if not self.files:
            messagebox.showwarning('ファイル未選択', 'MP3ファイルを追加してください。')
            return
        ffmpeg = ffmpeg_path()
        if not ffmpeg:
            messagebox.showerror('FFmpegがありません', 'ffmpeg.exeをmain.pyと同じフォルダに置くか、PATHに追加してください。')
            return
        dest = Path(self.output_dir.get()).expanduser()
        try: dest.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror('出力先エラー', str(e))
            return
        self.running = True
        for w in (self.add_btn, self.remove_btn, self.clear_btn, self.browse_btn, self.depth_combo, self.rate_combo, self.convert_btn):
            w.configure(state='disabled')
        self.progress.configure(maximum=len(self.files), value=0)
        self.status.set('変換を開始しています…')
        threading.Thread(target=self.worker, args=(list(self.files), dest, ffmpeg, self.bit_depth.get(), self.sample_rate.get()), daemon=True).start()

    def worker(self, files, dest, ffmpeg, depth, rate):
        errors = []
        for i, src in enumerate(files, 1):
            name = Path(src).stem
            target = dest / (name + '.wav')
            suffix = 2
            while target.exists():
                target = dest / f'{name}_{suffix}.wav'
                suffix += 1
            args = [ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-i', src, '-vn', '-c:a', 'pcm_s16le' if depth == '16bit' else 'pcm_s24le']
            if rate != '元のまま': args += ['-ar', rate]
            args += ['-y', str(target)]
            try:
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                result = subprocess.run(args, capture_output=True, text=True, errors='replace', creationflags=flags)
                if result.returncode != 0:
                    errors.append(f'{Path(src).name}: {result.stderr.strip()[-300:]}')
                    try: target.unlink(missing_ok=True)
                    except OSError: pass
            except Exception as e:
                errors.append(f'{Path(src).name}: {e}')
            self.events.put(('progress', i, len(files)))
        self.events.put(('done', len(files), errors))

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == 'progress':
                    self.progress['value'] = event[1]
                    self.status.set(f'処理済み: {event[1]} / {event[2]}')
                elif event[0] == 'done':
                    self.running = False
                    for w in (self.add_btn, self.remove_btn, self.clear_btn, self.browse_btn, self.depth_combo, self.rate_combo, self.convert_btn):
                        w.configure(state='normal')
                    self.depth_combo.configure(state='readonly')
                    self.rate_combo.configure(state='readonly')
                    count, errors = event[1], event[2]
                    self.status.set(f'完了: 成功 {count - len(errors)} 件 / 失敗 {len(errors)} 件')
                    if errors:
                        messagebox.showwarning('変換結果', f'成功 {count-len(errors)} 件 / 失敗 {len(errors)} 件\n\n' + '\n'.join(errors[:8]))
                    else:
                        messagebox.showinfo('変換完了', f'{count} 件の変換が完了しました。')
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

if __name__ == '__main__':
    root = Root()
    App(root)
    root.mainloop()
