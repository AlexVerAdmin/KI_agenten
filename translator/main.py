#!/usr/bin/env python3
"""
Screen Translator
Горячая клавиша + скриншот + OCR (tesseract) + перевод через DeepL API

Требования (Linux/X11):
  sudo apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-rus
  pip install -r requirements.txt

Запуск: python3 main.py
Горячая клавиша по умолчанию: Ctrl+Shift+T
"""

from __future__ import annotations

import json
import os
import sys
import socket
import threading
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

try:
    from PIL import Image, ImageDraw, ImageTk
    import pytesseract
    import deepl
    from pynput import keyboard as pynput_kb
    import mss
    import pystray
except ImportError as _exc:
    sys.exit(
        f"ImportError: {_exc}\n"
        "Установите зависимости:\n  pip install -r requirements.txt"
    )

# ── Config ────────────────────────────────────────────────────────────────────

import time
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

_CFG_FILE = os.path.expanduser("~/.config/screen-translator/config.json")
_DEFAULTS: dict = {
    "deepl_api_key": os.getenv("DEEPL_API_KEY", ""),
    "target_lang": "RU",
    "source_lang": "",          # "" = авто
    "hotkey": "double_ctrl_c",
    "ocr_lang": "eng+deu+rus",
    "fav_src": [],
    "fav_tgt": ["RU"],
}


def load_cfg() -> dict:
    if os.path.exists(_CFG_FILE):
        try:
            with open(_CFG_FILE, encoding="utf-8") as f:
                return {**_DEFAULTS, **json.load(f)}
        except Exception:
            pass
    return _DEFAULTS.copy()


def save_cfg(cfg: dict) -> None:
    os.makedirs(os.path.dirname(_CFG_FILE), exist_ok=True)
    with open(_CFG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ── Quick Choice Menu ───────────────────────────────────────────────────────

class QuickMenu(tk.Toplevel):
    """Маленькое всплывающее меню выбора режима по горячей клавише."""

    def __init__(self, parent: tk.Misc, on_clipboard: Callable, on_screenshot: Callable) -> None:
        super().__init__(parent)
        self._on_clipboard = on_clipboard
        self._on_screenshot = on_screenshot

        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#2b2b2b")

        # Центрируем на экране
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        frm = tk.Frame(self, bg="#2b2b2b", padx=2, pady=2)
        frm.pack(fill="both", expand=True)

        tk.Label(
            frm, text="Screen Translator",
            bg="#2b2b2b", fg="#aaaaaa",
            font=("Sans", 9),
        ).pack(padx=16, pady=(10, 6))

        btn_style = dict(
            bg="#3c3f41", fg="white", activebackground="#4c7cf4",
            activeforeground="white", relief="flat",
            font=("Sans", 12), cursor="hand2",
            padx=20, pady=10, bd=0,
        )

        b1 = tk.Button(frm, text="�  Перевести выделенный текст", **btn_style,
                       command=self._pick_screenshot)
        b1.pack(fill="x", padx=8, pady=(0, 4))

        b2 = tk.Button(frm, text="📸  Выделить область экрана", **btn_style,
                       command=self._pick_text)
        b2.pack(fill="x", padx=8, pady=(0, 10))

        tk.Label(
            frm, text="Esc — закрыть",
            bg="#2b2b2b", fg="#666666", font=("Sans", 8),
        ).pack(pady=(0, 6))

        self.update_idletasks()
        w, h = self.winfo_width(), self.winfo_height()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"+{x}+{y}")

        self.bind("<Escape>", lambda _: self.destroy())
        self.bind("<FocusOut>", lambda _: self.destroy())
        b1.bind("<Enter>", lambda e: b1.config(bg="#4c7cf4"))
        b1.bind("<Leave>", lambda e: b1.config(bg="#3c3f41"))
        b2.bind("<Enter>", lambda e: b2.config(bg="#4c7cf4"))
        b2.bind("<Leave>", lambda e: b2.config(bg="#3c3f41"))
        self.focus_force()

    def _pick_screenshot(self) -> None:
        self.destroy()
        self._on_clipboard()

    def _pick_text(self) -> None:
        self.destroy()
        self._on_screenshot()


# ── Region Selector ──────────────────────────────────────────────────────────

class RegionSelector(tk.Toplevel):
    """Оверлей выбора области: фон — затемнённый скриншот, выделение — оригинал."""

    def __init__(self, parent: tk.Misc, callback: Callable) -> None:
        super().__init__(parent)
        self._cb = callback
        self._sx = self._sy = 0
        self._rect: Optional[int] = None
        self._inner_id: Optional[int] = None
        self._inner_tk = None

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()

        # Снимок до показа оверлея (окно ещё не видно)
        with mss.mss() as sct:
            raw = sct.grab({"top": 0, "left": 0, "width": sw, "height": sh})
            orig = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        self._orig = orig

        # Затемнённый фон через PIL — не нужен window -alpha
        dark = Image.new("RGBA", (sw, sh), (0, 0, 0, 60))
        bg = Image.alpha_composite(orig.convert("RGBA"), dark).convert("RGB")
        self._bg_tk = ImageTk.PhotoImage(bg)

        self.overrideredirect(True)
        self.geometry(f"{sw}x{sh}+0+0")
        self.attributes("-topmost", True)
        self.config(cursor="crosshair")
        self.update()

        cv = tk.Canvas(self, width=sw, height=sh, highlightthickness=0, cursor="crosshair")
        cv.place(x=0, y=0)
        cv.create_image(0, 0, anchor="nw", image=self._bg_tk)
        cv.create_text(
            sw // 2, 30,
            text="Выделите область   ·   Escape — отмена",
            fill="white", font=("Sans", 14, "bold"),
        )
        self._cv = cv
        self.focus_force()

        cv.bind("<ButtonPress-1>",   self._press)
        cv.bind("<B1-Motion>",       self._drag)
        cv.bind("<ButtonRelease-1>", self._release)
        self.bind("<Escape>",        lambda _: self.destroy())
        cv.bind("<Escape>",          lambda _: self.destroy())

    def _press(self, e: tk.Event) -> None:
        self._sx, self._sy = e.x_root, e.y_root

    def _drag(self, e: tk.Event) -> None:
        cv = self._cv
        if self._rect is not None:
            cv.delete(self._rect)
        if self._inner_id is not None:
            cv.delete(self._inner_id)
        x1, y1 = min(self._sx, e.x_root), min(self._sy, e.y_root)
        x2, y2 = max(self._sx, e.x_root), max(self._sy, e.y_root)
        if x2 > x1 and y2 > y1:
            # Показываем оригинальный (яркий) фрагмент внутри выделения
            crop = self._orig.crop((x1, y1, x2, y2))
            self._inner_tk = ImageTk.PhotoImage(crop)
            self._inner_id = cv.create_image(x1, y1, anchor="nw", image=self._inner_tk)
        self._rect = cv.create_rectangle(x1, y1, x2, y2, outline="#1a73e8", width=2)

    def _release(self, e: tk.Event) -> None:
        x1, y1 = min(self._sx, e.x_root), min(self._sy, e.y_root)
        x2, y2 = max(self._sx, e.x_root), max(self._sy, e.y_root)
        self.destroy()
        if (x2 - x1) > 8 and (y2 - y1) > 8:
            self._cb(x1, y1, x2, y2)


# ── Result Window ─────────────────────────────────────────────────────────────

class ResultWindow(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        original: str,
        translated: str,
        cfg: dict,
        retranslate: Callable,
    ) -> None:
        super().__init__(parent)
        self.title("Перевод — Screen Translator")
        self.attributes("-topmost", True)
        self.geometry("680x520")
        self.resizable(True, True)
        self._retranslate = retranslate
        self._cfg = cfg
        self._selecting = False

        # ── Оригинал ─────────────────────────────────────────────────────────
        src_bar = ttk.Frame(self)
        src_bar.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(src_bar, text="Оригинал:").pack(side="left")
        names, self._src_codes = _lang_combo_build(_LANGS_SRC, cfg.get("fav_src", []))
        self._src_cb = ttk.Combobox(src_bar, values=names, state="readonly", width=26)
        self._src_cb_set(cfg.get("source_lang", ""))
        self._src_cb.pack(side="left", padx=(6, 2))
        self._src_cb.bind("<<ComboboxSelected>>", lambda _: self._on_src_select())
        ttk.Button(src_bar, text="×", width=3, command=self._remove_fav_src).pack(side="left")

        self._orig_box = scrolledtext.ScrolledText(
            self, wrap="word", font=("Sans", 11), bg="#f5f5f5", relief="flat", height=7)
        self._orig_box.insert("1.0", original)
        self._orig_box.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # ── Перевод ───────────────────────────────────────────────────────────
        tgt_bar = ttk.Frame(self)
        tgt_bar.pack(fill="x", padx=8, pady=(2, 2))
        ttk.Label(tgt_bar, text="Перевод:").pack(side="left")
        names, self._tgt_codes = _lang_combo_build(_LANGS_TGT, cfg.get("fav_tgt", ["RU"]))
        self._tgt_cb = ttk.Combobox(tgt_bar, values=names, state="readonly", width=26)
        self._tgt_cb_set(cfg.get("target_lang", "RU"))
        self._tgt_cb.pack(side="left", padx=(6, 2))
        self._tgt_cb.bind("<<ComboboxSelected>>", lambda _: self._on_tgt_select())
        ttk.Button(tgt_bar, text="×", width=3, command=self._remove_fav_tgt).pack(side="left")

        self._trans_box = scrolledtext.ScrolledText(
            self, wrap="word", font=("Sans", 11), bg="#f0f7f0", relief="flat", height=7)
        self._trans_box.insert("1.0", translated)
        self._trans_box.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(
            bar, text="📋  Копировать перевод",
            command=lambda: self._copy(self._trans_box.get("1.0", "end").strip()),
        ).pack(side="left")
        ttk.Button(bar, text="Закрыть", command=self.destroy).pack(side="right")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _src_cb_set(self, code: str) -> None:
        try:
            self._src_cb.current(self._src_codes.index(code))
        except ValueError:
            self._src_cb.current(0)

    def _tgt_cb_set(self, code: str) -> None:
        try:
            self._tgt_cb.current(self._tgt_codes.index(code))
        except ValueError:
            self._tgt_cb.current(0)

    def _current_src(self) -> str:
        idx = self._src_cb.current()
        return self._src_codes[idx] if 0 <= idx < len(self._src_codes) else ""

    def _current_tgt(self) -> str:
        idx = self._tgt_cb.current()
        return self._tgt_codes[idx] if 0 <= idx < len(self._tgt_codes) else "RU"

    def _rebuild_src(self, keep: str) -> None:
        self._src_cb.unbind("<<ComboboxSelected>>")
        names, self._src_codes = _lang_combo_build(_LANGS_SRC, self._cfg.get("fav_src", []))
        self._src_cb.config(values=names)
        self._src_cb_set(keep)
        self._src_cb.bind("<<ComboboxSelected>>", lambda _: self._on_src_select())

    def _rebuild_tgt(self, keep: str) -> None:
        self._tgt_cb.unbind("<<ComboboxSelected>>")
        names, self._tgt_codes = _lang_combo_build(_LANGS_TGT, self._cfg.get("fav_tgt", []))
        self._tgt_cb.config(values=names)
        self._tgt_cb_set(keep)
        self._tgt_cb.bind("<<ComboboxSelected>>", lambda _: self._on_tgt_select())

    # ── events ────────────────────────────────────────────────────────────────

    def _on_src_select(self) -> None:
        if self._selecting:
            return
        self._selecting = True
        try:
            code = self._current_src()
            if code == _FAV_SEP_CODE:
                self._src_cb_set(self._cfg.get("source_lang", ""))
                return
            self._cfg["source_lang"] = code
            favs = self._cfg.get("fav_src", [])
            if code not in favs:
                self._cfg["fav_src"] = [code] + favs
            save_cfg(self._cfg)
            self._rebuild_src(code)
            self._do_translate()
        finally:
            self._selecting = False

    def _on_tgt_select(self) -> None:
        if self._selecting:
            return
        self._selecting = True
        try:
            code = self._current_tgt()
            if code == _FAV_SEP_CODE:
                self._tgt_cb_set(self._cfg.get("target_lang", "RU"))
                return
            self._cfg["target_lang"] = code
            favs = self._cfg.get("fav_tgt", [])
            if code not in favs:
                self._cfg["fav_tgt"] = [code] + favs
            save_cfg(self._cfg)
            self._rebuild_tgt(code)
            self._do_translate()
        finally:
            self._selecting = False

    def _remove_fav_src(self) -> None:
        code = self._current_src()
        if code == _FAV_SEP_CODE:
            return
        self._cfg["fav_src"] = [f for f in self._cfg.get("fav_src", []) if f != code]
        save_cfg(self._cfg)
        self._rebuild_src(code)

    def _remove_fav_tgt(self) -> None:
        code = self._current_tgt()
        if code == _FAV_SEP_CODE:
            return
        self._cfg["fav_tgt"] = [f for f in self._cfg.get("fav_tgt", []) if f != code]
        save_cfg(self._cfg)
        self._rebuild_tgt(code)

    def _do_translate(self) -> None:
        src = self._current_src()
        tgt = self._current_tgt()
        if _FAV_SEP_CODE in (src, tgt):
            return
        text = self._orig_box.get("1.0", "end").strip()
        if not text:
            return
        self._trans_box.delete("1.0", "end")
        self._trans_box.insert("1.0", "…")
        self._retranslate(text, src, tgt, self._trans_box)

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update()


# ── Language lists ────────────────────────────────────────────────────────────

_LANGS_SRC = sorted([
    ("",     "Авто (определить)"),
    ("BG",   "Болгарский"),   ("CS",   "Чешский"),      ("DA",   "Датский"),
    ("DE",   "Немецкий"),   ("EL",   "Греческий"),   ("EN",   "Английский"),
    ("ES",   "Испанский"),   ("ET",   "Эстонский"),   ("FI",   "Финский"),
    ("FR",   "Французский"),  ("HU",   "Венгерский"),   ("ID",   "Индонезийский"),
    ("IT",   "Итальянский"),  ("JA",   "Японский"),    ("KO",   "Корейский"),
    ("LT",   "Литовский"),   ("LV",   "Латвийский"),   ("NB",   "Норвежский"),
    ("NL",   "Нидерландский"),  ("PL",   "Польский"),
    ("PT",   "Португальский"),
    ("RO",   "Румынский"),   ("RU",   "Русский"),      ("SK",   "Словацкий"),
    ("SL",   "Словенский"),   ("SV",   "Шведский"),    ("TR",   "Турецкий"),
    ("UK",   "Украинский"),   ("ZH",   "Китайский"),
], key=lambda p: (p[0] != "", p[1]))

_LANGS_TGT = sorted([
    ("BG",      "Болгарский"),       ("CS",      "Чешский"),
    ("DA",      "Датский"),         ("DE",      "Немецкий"),
    ("EL",      "Греческий"),       ("EN-GB",   "Английский (UK)"),
    ("EN-US",   "Английский (US)"),  ("ES",      "Испанский"),
    ("ET",      "Эстонский"),       ("FI",      "Финский"),
    ("FR",      "Французский"),      ("HU",      "Венгерский"),
    ("ID",      "Индонезийский"),    ("IT",      "Итальянский"),
    ("JA",      "Японский"),        ("KO",      "Корейский"),
    ("LT",      "Литовский"),       ("LV",      "Латвийский"),
    ("NB",      "Норвежский"),      ("NL",      "Нидерландский"),
    ("PL",      "Польский"),        ("PT-BR",   "Португальский (BR)"),
    ("PT-PT",   "Португальский (PT)"),  ("RO",      "Румынский"),
    ("RU",      "Русский"),        ("SK",      "Словацкий"),
    ("SL",      "Словенский"),      ("SV",      "Шведский"),
    ("TR",      "Турецкий"),       ("UK",      "Украинский"),
    ("ZH-HANS", "Китайский (упр.)"),  ("ZH-HANT", "Китайский (трад.)"),
], key=lambda p: p[1])

_FAV_SEP_CODE = "__sep__"


def _lang_combo_build(all_pairs: list, favs: list) -> tuple:
    """Избранные — вверху (со звёздочкой), затем разделитель, затем остальные."""
    fav_set = set(favs)
    fav_p  = [(c, n) for c, n in all_pairs if c in fav_set]
    rest_p = [(c, n)            for c, n in all_pairs if c not in fav_set]
    if fav_p and rest_p:
        pairs = fav_p + [(_FAV_SEP_CODE, "─" * 20)] + rest_p
    else:
        pairs = fav_p + rest_p
    return [n for _, n in pairs], [c for c, _ in pairs]


# ── Settings Dialog ───────────────────────────────────────────────────────────

class SettingsDlg(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        cfg: dict,
        on_save: Callable[[dict], None],
    ) -> None:
        super().__init__(parent)
        self.title("Настройки — Screen Translator")
        self.resizable(False, False)
        self.grab_set()
        self._on_save = on_save
        self._cfg = cfg.copy()

        p = {"padx": 10, "pady": 6, "sticky": "w"}

        # ── API key ──────────────────────────────────────────────────────────
        ttk.Label(self, text="DeepL API ключ:").grid(row=0, column=0, **p)
        self._api_var = tk.StringVar(value=cfg.get("deepl_api_key", ""))
        self._api_entry = ttk.Entry(
            self, textvariable=self._api_var, width=44, show="*"
        )
        self._api_entry.grid(row=0, column=1, columnspan=2, **p)
        self._show_var = tk.BooleanVar()
        ttk.Checkbutton(
            self, text="Показать", variable=self._show_var,
            command=lambda: self._api_entry.config(
                show="" if self._show_var.get() else "*"
            ),
        ).grid(row=0, column=3, **p)

        # ── Source lang ───────────────────────────────────────────────────────
        self._src_codes = [c for c, _ in _LANGS_SRC]
        ttk.Label(self, text="Язык источника:").grid(row=1, column=0, **p)
        self._src_box = ttk.Combobox(
            self, values=[n for _, n in _LANGS_SRC],
            state="readonly", width=22,
        )
        try:
            self._src_box.current(
                self._src_codes.index(cfg.get("source_lang", ""))
            )
        except ValueError:
            self._src_box.current(0)
        self._src_box.grid(row=1, column=1, **p)

        # ── Target lang ───────────────────────────────────────────────────────
        self._tgt_codes = [c for c, _ in _LANGS_TGT]
        ttk.Label(self, text="Язык перевода:").grid(row=2, column=0, **p)
        self._tgt_box = ttk.Combobox(
            self, values=[n for _, n in _LANGS_TGT],
            state="readonly", width=22,
        )
        try:
            self._tgt_box.current(
                self._tgt_codes.index(cfg.get("target_lang", "RU"))
            )
        except ValueError:
            self._tgt_box.current(self._tgt_codes.index("RU"))
        self._tgt_box.grid(row=2, column=1, **p)

        # ── OCR ───────────────────────────────────────────────────────────────
        ttk.Label(self, text="OCR языки:").grid(row=3, column=0, **p)
        self._ocr_var = tk.StringVar(value=cfg.get("ocr_lang", "eng+deu+rus"))
        ttk.Entry(self, textvariable=self._ocr_var, width=24).grid(
            row=3, column=1, **p
        )
        ttk.Label(
            self, text="(коды tesseract через +: eng, deu, rus, ukr…)",
            foreground="gray",
        ).grid(row=3, column=2, columnspan=2, **p)

        # ── Hotkey (info only) ────────────────────────────────────────────────
        ttk.Label(self, text="Горячая клавиша:").grid(row=4, column=0, **p)
        ttk.Label(
            self, text="Ctrl+C+C (дважды, независимо от разкладки)",
            foreground="gray",
        ).grid(row=4, column=1, columnspan=3, **p)

        # ── Hint ──────────────────────────────────────────────────────────────
        ttk.Label(
            self, text="Бесплатный ключ DeepL оканчивается на :fx",
            foreground="#0055cc",
        ).grid(row=5, column=0, columnspan=4, padx=10, pady=6)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_f = ttk.Frame(self)
        btn_f.grid(row=6, column=0, columnspan=4, pady=10)
        ttk.Button(
            btn_f, text="Тест соединения", command=self._test
        ).pack(side="left", padx=4)
        ttk.Button(
            btn_f, text="Сохранить", command=self._save
        ).pack(side="left", padx=4)
        ttk.Button(btn_f, text="Отмена", command=self.destroy).pack(side="left")

    def _test(self) -> None:
        key = self._api_var.get().strip()
        if not key:
            messagebox.showwarning("Ключ не задан", "Введите API ключ.", parent=self)
            return
        try:
            tr = deepl.Translator(key)
            usage = tr.get_usage()
            messagebox.showinfo(
                "Соединение OK",
                f"Использовано символов: {usage.character.count:,} "
                f"из {usage.character.limit:,}",
                parent=self,
            )
        except deepl.AuthorizationException:
            messagebox.showerror("Ошибка", "Неверный API ключ.", parent=self)
        except Exception as exc:
            messagebox.showerror("Ошибка", str(exc), parent=self)

    def _save(self) -> None:
        self._cfg.update({
            "deepl_api_key": self._api_var.get().strip(),
            "source_lang":   self._src_codes[self._src_box.current()],
            "target_lang":   self._tgt_codes[self._tgt_box.current()],
            "ocr_lang":      self._ocr_var.get().strip(),
        })
        save_cfg(self._cfg)
        self._on_save(self._cfg)
        self.destroy()


# ── Main Application ──────────────────────────────────────────────────────────

class App:
    def __init__(self) -> None:
        self._ensure_single_instance()
        self.cfg = load_cfg()
        self._stop_evt = threading.Event()
        self._lang_selecting = False  # защита от повторного входа в select-хендлер

        self.root = tk.Tk()
        self.root.title("Screen Translator")
        self.root.resizable(False, False)
        self._build_ui()
        self._start_hotkey()
        self._setup_tray()
        self.root.protocol("WM_DELETE_WINDOW", self._hide_window)
        # Стартуем скрытыми — только трей/горячая клавиша
        self.root.withdraw()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._nb = nb

        # ── Tab: Текст ────────────────────────────────────────────────────────
        tab_txt = ttk.Frame(nb)
        nb.add(tab_txt, text="  Текст  ")

        # Строка: язык источника + ★ + кнопка Очистить
        src_bar = ttk.Frame(tab_txt)
        src_bar.pack(fill="x", padx=6, pady=(6, 0))
        ttk.Label(src_bar, text="Исходный текст:").pack(side="left")
        names_s, self._src_codes_bar = _lang_combo_build(
            _LANGS_SRC, self.cfg.get("fav_src", [])
        )
        self._lang_src_cb = ttk.Combobox(
            src_bar, values=names_s, state="readonly", width=22,
        )
        try:
            self._lang_src_cb.current(
                self._src_codes_bar.index(self.cfg.get("source_lang", ""))
            )
        except ValueError:
            self._lang_src_cb.current(0)
        self._lang_src_cb.pack(side="left", padx=(6, 2))
        self._lang_src_cb.bind("<<ComboboxSelected>>", lambda _: self._on_src_bar_select())
        ttk.Button(
            src_bar, text="×", width=3,
            command=self._remove_fav_src_bar,
        ).pack(side="left")
        ttk.Button(
            src_bar, text="Очистить",
            command=lambda: self._inp.delete("1.0", "end"),
        ).pack(side="right")

        self._inp = scrolledtext.ScrolledText(
            tab_txt, wrap="word", font=("Monospace", 11), width=56, height=8
        )
        self._inp.pack(fill="both", expand=True, padx=6, pady=(2, 0))

        # Строка: язык перевода + ★ + кнопка Перевести
        tgt_bar = ttk.Frame(tab_txt)
        tgt_bar.pack(fill="x", padx=6, pady=(4, 0))
        ttk.Label(tgt_bar, text="Перевод:").pack(side="left")
        names_t, self._tgt_codes_bar = _lang_combo_build(
            _LANGS_TGT, self.cfg.get("fav_tgt", ["RU"])
        )
        self._lang_tgt_cb = ttk.Combobox(
            tgt_bar, values=names_t, state="readonly", width=22,
        )
        try:
            self._lang_tgt_cb.current(
                self._tgt_codes_bar.index(self.cfg.get("target_lang", "RU"))
            )
        except ValueError:
            self._lang_tgt_cb.current(0)
        self._lang_tgt_cb.pack(side="left", padx=(6, 2))
        self._lang_tgt_cb.bind("<<ComboboxSelected>>", lambda _: self._on_tgt_bar_select())
        ttk.Button(
            tgt_bar, text="×", width=3,
            command=self._remove_fav_tgt_bar,
        ).pack(side="left")

        self._out = scrolledtext.ScrolledText(
            tab_txt, wrap="word", font=("Sans", 12),
            bg="#f0f7f0", width=56, height=8,
        )
        self._out.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        # ── Tab: Скриншот ─────────────────────────────────────────────────────
        tab_cap = ttk.Frame(nb)
        nb.add(tab_cap, text="  Скриншот  ")
        self._hk_lbl = ttk.Label(tab_cap, font=("Sans", 11))
        self._hk_lbl.pack(pady=20)
        self._refresh_hk_label()
        ttk.Button(
            tab_cap, text="  📸  Захватить область экрана  ",
            command=self._start_screenshot,
        ).pack(pady=6)
        ttk.Label(
            tab_cap,
            text="После нажатия выделите нужную область мышью.",
            foreground="gray",
        ).pack()

        # ── Tab: Настройки ────────────────────────────────────────────────────
        tab_cfg = ttk.Frame(nb)
        nb.add(tab_cfg, text="  Настройки  ")
        self._status_lbl = ttk.Label(tab_cfg, justify="center")
        self._status_lbl.pack(pady=(20, 8))
        self._refresh_status()
        ttk.Button(
            tab_cfg, text="Открыть настройки", command=self._settings
        ).pack()

    def _refresh_status(self) -> None:
        has = bool(self.cfg.get("deepl_api_key"))
        src = self.cfg.get("source_lang") or "Авто"
        tgt = self.cfg.get("target_lang", "RU")
        self._status_lbl.config(
            text=(
                f"API ключ: {'✓ задан' if has else '✗ не задан'}\n"
                f"Перевод: {src} → {tgt}\n"
                f"Ctrl+C+C — если выделен текст → перевод\n"
                f"если нет → выбор области экрана"
            )
        )

    def _refresh_hk_label(self) -> None:
        self._hk_lbl.config(text="Ctrl+C+C — выделен текст / нет → область экрана")

    def _on_src_bar_select(self) -> None:
        if self._lang_selecting:
            return
        self._lang_selecting = True
        try:
            idx = self._lang_src_cb.current()
            code = self._src_codes_bar[idx] if 0 <= idx < len(self._src_codes_bar) else ""
            if code == _FAV_SEP_CODE:
                try:
                    self._lang_src_cb.current(
                        self._src_codes_bar.index(self.cfg.get("source_lang", ""))
                    )
                except ValueError:
                    self._lang_src_cb.current(0)
                return
            self.cfg["source_lang"] = code
            favs = self.cfg.get("fav_src", [])
            if code not in favs:
                self.cfg["fav_src"] = [code] + favs
            save_cfg(self.cfg)
            self._rebuild_bar_src(code)
            self._refresh_status()
            if self._inp.get("1.0", "end").strip():
                self._tr_text()
        finally:
            self._lang_selecting = False

    def _on_tgt_bar_select(self) -> None:
        if self._lang_selecting:
            return
        self._lang_selecting = True
        try:
            idx = self._lang_tgt_cb.current()
            code = self._tgt_codes_bar[idx] if 0 <= idx < len(self._tgt_codes_bar) else "RU"
            if code == _FAV_SEP_CODE:
                try:
                    self._lang_tgt_cb.current(
                        self._tgt_codes_bar.index(self.cfg.get("target_lang", "RU"))
                    )
                except ValueError:
                    self._lang_tgt_cb.current(0)
                return
            self.cfg["target_lang"] = code
            favs = self.cfg.get("fav_tgt", [])
            if code not in favs:
                self.cfg["fav_tgt"] = [code] + favs
            save_cfg(self.cfg)
            self._rebuild_bar_tgt(code)
            self._refresh_status()
            if self._inp.get("1.0", "end").strip():
                self._tr_text()
        finally:
            self._lang_selecting = False

    def _remove_fav_src_bar(self) -> None:
        idx = self._lang_src_cb.current()
        code = self._src_codes_bar[idx] if 0 <= idx < len(self._src_codes_bar) else ""
        if code == _FAV_SEP_CODE:
            return
        self.cfg["fav_src"] = [f for f in self.cfg.get("fav_src", []) if f != code]
        save_cfg(self.cfg)
        self._rebuild_bar_src(code)

    def _remove_fav_tgt_bar(self) -> None:
        idx = self._lang_tgt_cb.current()
        code = self._tgt_codes_bar[idx] if 0 <= idx < len(self._tgt_codes_bar) else "RU"
        if code == _FAV_SEP_CODE:
            return
        self.cfg["fav_tgt"] = [f for f in self.cfg.get("fav_tgt", []) if f != code]
        save_cfg(self.cfg)
        self._rebuild_bar_tgt(code)

    def _rebuild_bar_src(self, keep_code: str) -> None:
        self._lang_src_cb.unbind("<<ComboboxSelected>>")
        names, self._src_codes_bar = _lang_combo_build(
            _LANGS_SRC, self.cfg.get("fav_src", [])
        )
        self._lang_src_cb.config(values=names)
        try:
            self._lang_src_cb.current(self._src_codes_bar.index(keep_code))
        except ValueError:
            self._lang_src_cb.current(0)
        self._lang_src_cb.bind("<<ComboboxSelected>>", lambda _: self._on_src_bar_select())

    def _rebuild_bar_tgt(self, keep_code: str) -> None:
        self._lang_tgt_cb.unbind("<<ComboboxSelected>>")
        names, self._tgt_codes_bar = _lang_combo_build(
            _LANGS_TGT, self.cfg.get("fav_tgt", [])
        )
        self._lang_tgt_cb.config(values=names)
        try:
            self._lang_tgt_cb.current(self._tgt_codes_bar.index(keep_code))
        except ValueError:
            self._lang_tgt_cb.current(0)
        self._lang_tgt_cb.bind("<<ComboboxSelected>>", lambda _: self._on_tgt_bar_select())

    def _refresh_lang_bar(self) -> None:
        self._rebuild_bar_src(self.cfg.get("source_lang", ""))
        self._rebuild_bar_tgt(self.cfg.get("target_lang", "RU"))

    # ── Hotkey listener ───────────────────────────────────────────────────────

    def _start_hotkey(self) -> None:
        self._stop_evt = threading.Event()
        stop = self._stop_evt
        _c_count: list[int]    = [0]
        _last_c:  list[float]  = [0.0]
        _ctrl:    list[bool]   = [False]
        _timer_id: list[Optional[str]] = [None]
        _INTERVAL = 0.5  # Макс интервал между нажатиями

        def dispatch() -> None:
            count = _c_count[0]
            _c_count[0] = 0
            _last_c[0] = 0.0
            _timer_id[0] = None
            if count == 2:
                # 2 раза Ctrl+C -> скриншот
                self.root.after(0, self._start_screenshot)
            elif count >= 3:
                # 3 и более раза Ctrl+C -> текст из буфера
                self.root.after(0, self._translate_from_selection)

        def on_press(key: pynput_kb.Key) -> Optional[bool]:
            if stop.is_set():
                return False
            if key in (pynput_kb.Key.ctrl_l, pynput_kb.Key.ctrl_r):
                _ctrl[0] = True
                return None
            if _ctrl[0]:
                try:
                    char = key.char
                except AttributeError:
                    char = None
                
                if char is not None and char.lower() == 'c':
                    now = time.monotonic()
                    # Если нажатие в рамках интервала
                    if now - _last_c[0] <= _INTERVAL or _c_count[0] == 0:
                        _c_count[0] += 1
                        _last_c[0] = now
                        
                        # Отменяем старый таймер и ставим новый
                        if _timer_id[0]:
                            self.root.after_cancel(_timer_id[0])
                        _timer_id[0] = self.root.after(int(_INTERVAL*1000), dispatch)
                    else:
                        # Интервал превышен, сбрасываем как первое нажатие
                        _c_count[0] = 1
                        _last_c[0] = now
                        if _timer_id[0]:
                            self.root.after_cancel(_timer_id[0])
                        _timer_id[0] = self.root.after(int(_INTERVAL*1000), dispatch)
            return None

        def on_release(key: pynput_kb.Key) -> Optional[bool]:
            if stop.is_set():
                return False
            if key in (pynput_kb.Key.ctrl_l, pynput_kb.Key.ctrl_r):
                _ctrl[0] = False
            return None

        def run() -> None:
            with pynput_kb.Listener(on_press=on_press, on_release=on_release) as lst:
                stop.wait()
                lst.stop()

        threading.Thread(target=run, daemon=True).start()

    # ── Capture flow ──────────────────────────────────────────────────────────

    def _hotkey_action(self) -> None:
        """Если есть выделенный текст — перевести его. Иначе — скриншот."""
        text = ""
        try:
            text = self.root.selection_get(selection="PRIMARY").strip()
        except tk.TclError:
            pass
        if text:
            self._translate_text(text)
        else:
            self._start_screenshot()

    def _start_text_mode(self) -> None:
        """Показать подсказку для ручного выделения текста."""
        TextSelectionHint(
            self.root,
            on_confirm=self._translate_from_selection,
            on_cancel=lambda: None,
        )

    def _translate_from_selection(self) -> None:
        """Взять текст из PRIMARY selection или CLIPBOARD и перевести."""
        text = ""
        try:
            text = self.root.selection_get(selection="PRIMARY").strip()
        except tk.TclError:
            pass
        if not text:
            try:
                text = self.root.clipboard_get().strip()
            except tk.TclError:
                pass
        if not text:
            messagebox.showwarning(
                "Нет текста",
                "Текст не найден.\n"
                "Убедитесь, что текст выделен мышью или скопирован."
            )
            return
        self._translate_text(text)

    def _translate_text(self, text: str) -> None:
        """Перевести текст и показать окно результата."""
        def worker() -> None:
            translated = self._call_ollama(text)
            if translated is not None:
                self.root.after(0, lambda t=text, tr=translated:
                    ResultWindow(self.root, t, tr, self.cfg, self._retranslate_in_window))
        threading.Thread(target=worker, daemon=True).start()

    def _retranslate_in_window(self, text: str, src: str, tgt: str, out_box: scrolledtext.ScrolledText) -> None:
        """Повторный перевод с другими языками прямо в ResultWindow."""
        def worker() -> None:
            try:
                result = self._call_ollama(text, src, tgt)
                if result:
                    self.root.after(0, lambda r=result: (
                        out_box.delete("1.0", "end"),
                        out_box.insert("1.0", r),
                    ))
            except Exception as exc:
                self.root.after(0, lambda e=exc: messagebox.showerror("Ошибка Ollama", str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def _start_screenshot(self) -> None:
        """Скрыть всё и показать оверлей выделения области."""
        self.root.withdraw()
        self.root.after(150, self._open_selector)

    def _open_selector(self) -> None:
        RegionSelector(self.root, self._on_region)

    def _on_region(self, x1: int, y1: int, x2: int, y2: int) -> None:
        # Небольшая задержка, чтобы оверлей успел исчезнуть с экрана
        self.root.after(150, lambda: self._grab_worker(x1, y1, x2, y2))

    def _grab_worker(self, x1: int, y1: int, x2: int, y2: int) -> None:
        def worker() -> None:
            try:
                with mss.mss() as sct:
                    raw = sct.grab({
                        "top": y1, "left": x1,
                        "width": x2 - x1, "height": y2 - y1,
                    })
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

                ocr_lang = self.cfg.get("ocr_lang", "eng")
                text = pytesseract.image_to_string(img, lang=ocr_lang).strip()

                if not text:
                    self.root.after(0, lambda: messagebox.showwarning(
                        "OCR",
                        "Текст не распознан.\n\n"
                        "Убедитесь, что языковые пакеты tesseract установлены:\n"
                        "  sudo apt install tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-rus",
                    ))
                    return

                translated = self._call_ollama(text)
                if translated is not None:
                    self.root.after(
                        0, lambda t=text, tr=translated:
                        ResultWindow(self.root, t, tr, self.cfg, self._retranslate_in_window)
                    )
                    # Прячем главное окно — показываем только результат
                    self.root.after(0, self.root.withdraw)

            except Exception as exc:
                self.root.after(
                    0, lambda e=exc: messagebox.showerror("Ошибка", str(e))
                )

        threading.Thread(target=worker, daemon=True).start()

    # ── Text translation ──────────────────────────────────────────────────────

    def _tr_text(self) -> None:
        text = self._inp.get("1.0", "end").strip()
        if not text:
            return

        def worker() -> None:
            translated = self._call_ollama(text)
            if translated is not None:
                def update(t: str = translated) -> None:
                    self._out.delete("1.0", "end")
                    self._out.insert("1.0", t)
                self.root.after(0, update)

        threading.Thread(target=worker, daemon=True).start()

    # ── Ollama API ─────────────────────────────────────────────────────────────

    def _call_ollama(self, text: str, src: str = None, tgt: str = None) -> Optional[str]:
        """Локальный перевод через Ollama (Gemma 4:e4b)."""
        import requests
        
        target_lang = tgt or self.cfg.get("target_lang", "RU")
        # Упрощаем коды языков для модели
        lang_map = {"RU": "Russian", "UK": "Ukrainian", "EN": "English", "DE": "German"}
        target_full = lang_map.get(target_lang, target_lang)
        
        prompt = (
            f"Translate the following text into {target_full}. "
            f"Output ONLY the translated text, nothing else. No explanations, no quotes.\n\n"
            f"Text: {text}"
        )
        
        try:
            response = requests.post(
                "http://192.168.88.55:11434/api/generate",
                json={
                    "model": "gemma4:e4b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 500
                    }
                },
                timeout=60
            )
            if response.status_code == 200:
                result = response.json().get("response", "").strip()
                # Очистка от возможных артефактов (иногда модели пишут "Here is the translation:")
                if "\n" in result and len(result.split("\n")[0]) < 30 and ":" in result.split("\n")[0]:
                    result = "\n".join(result.split("\n")[1:]).strip()
                return result
            else:
                self.root.after(0, lambda: messagebox.showerror("Ошибка Ollama", f"Status: {response.status_code}"))
        except Exception as exc:
            self.root.after(0, lambda e=exc: messagebox.showerror("Ошибка Ollama", f"Убедитесь, что Ollama запущена\n{str(e)}"))
        return None

    # ── DeepL API ─────────────────────────────────────────────────────────────

    def _call_deepl(self, text: str) -> Optional[str]:
        key = self.cfg.get("deepl_api_key", "").strip()
        if not key:
            self.root.after(0, lambda: messagebox.showwarning(
                "API ключ", "DeepL API ключ не задан.\nОткройте вкладку «Настройки»."
            ))
            return None
        try:
            tr = deepl.Translator(key)
            src = self.cfg.get("source_lang") or None
            tgt = self.cfg.get("target_lang", "RU")
            return tr.translate_text(text, source_lang=src, target_lang=tgt).text
        except deepl.AuthorizationException:
            self.root.after(0, lambda: messagebox.showerror(
                "Авторизация", "Неверный DeepL API ключ."
            ))
        except Exception as exc:
            self.root.after(
                0, lambda e=exc: messagebox.showerror("Ошибка DeepL", str(e))
            )
        return None

    # ── Settings ──────────────────────────────────────────────────────────────

    def _settings(self) -> None:
        def on_save(new_cfg: dict) -> None:
            self.cfg = new_cfg
            self._stop_evt.set()
            self._start_hotkey()
            self._refresh_status()
            self._refresh_hk_label()
            self._refresh_lang_bar()

        SettingsDlg(self.root, self.cfg, on_save)

    def _open_settings(self) -> None:
        self._do_show_window()
        self.root.after(100, self._settings)

    # ── Tray ──────────────────────────────────────────────────────────────────

    def _make_tray_image(self) -> Image.Image:
        size = 64
        # Прозрачный фон
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        
        # 1. Рисуем черную обводку (чуть шире)
        # Горизонтальная перекладина обводки
        d.rectangle([10, 14, 54, 24], fill="black")
        # Вертикальная ножка обводки
        d.rectangle([26, 24, 38, 54], fill="black")
        
        # 2. Рисуем белую заливку поверх
        # Горизонтальная перекладина внутренняя
        d.rectangle([12, 16, 52, 22], fill="white")
        # Вертикальная ножка внутренняя
        d.rectangle([28, 22, 36, 52], fill="white")
        
        return img

    def _setup_tray(self) -> None:
        menu = pystray.Menu(
            pystray.MenuItem("�  Ctrl+C+C — перевести", lambda icon, item: self.root.after(0, self._hotkey_action), default=True),
            pystray.MenuItem("📝  Выделить текст  (Ctrl+C+C)", lambda icon, item: self.root.after(0, self._start_text_mode)),
            pystray.MenuItem("📝  Открыть переводчик", lambda icon, item: self._show_window()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("⚙  Настройки", lambda icon, item: self.root.after(0, self._open_settings)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Выход", self._quit),
        )
        self._tray = pystray.Icon(
            "screen-translator",
            self._make_tray_image(),
            "Screen Translator  [Ctrl+Shift+T]",
            menu,
        )
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _show_window(self, icon=None, item=None) -> None:
        self.root.after(0, self._do_show_window)

    def _do_show_window(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def _hide_window(self) -> None:
        self.root.iconify()

    # ── Quit ──────────────────────────────────────────────────────────────────

    def _quit(self, icon=None, item=None) -> None:
        self._stop_evt.set()
        try:
            self._tray.stop()
        except Exception:
            pass
        self.root.after(0, lambda: (self.root.destroy(), sys.exit(0)))

    def _ensure_single_instance(self) -> None:
        """Простая проверка через Unix socket, чтобы не запускать копии."""
        # Используем абстрактный сокет (начинается с \0), он удаляется ОС автоматически
        try:
            self._lock_socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
            self._lock_socket.bind('\0screen_translator_lock')
        except socket.error:
            # Если сокет занят — значит уже запущен другой экземпляр
            print("Another instance is already running.", file=sys.stderr)
            sys.exit(0)

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
