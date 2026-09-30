import customtkinter as ctk
from ui.constants import THEME


class ThemedDropdown(ctk.CTkFrame):
    """
    Dropdown modern kustom dengan styling yang sinkron dengan tema dark Mavdown.
    Menghilangkan border putih bawaan OS pada tkinter.Menu, memberikan border & pembatas
    yang tegas, warna kontras yang rapi, dan popup menu beranimasi dengan indicator aktif.
    """
    def __init__(
        self,
        master,
        values: list,
        default_value: str = None,
        command = None,
        placeholder: str = "Pilih Opsi...",
        height: int = 38,
        width: int = None,
        **kwargs
    ):
        super().__init__(
            master,
            fg_color="#0D0E1A",
            border_width=1,
            border_color=THEME["border_light"],
            corner_radius=8,
            height=height,
            **kwargs
        )
        if width:
            self.configure(width=width)

        self.values = list(values) if values else []
        self.command = command
        self._current_value = default_value if (default_value and default_value in self.values) else (self.values[0] if self.values else "")
        self.popup = None
        self._bind_click_id = None
        self._bind_scroll_id = None
        self._bind_cfg_id = None
        self._bind_esc_id = None

        # Setup grid
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=0)
        self.grid_rowconfigure(0, weight=1)

        # Label Teks Pilihan
        display_text = self._current_value or placeholder
        self.lbl_text = ctk.CTkLabel(
            self,
            text=display_text,
            font=ctk.CTkFont(family="Inter", size=12, weight="bold"),
            text_color=THEME["text_title"],
            anchor="w"
        )
        self.lbl_text.grid(row=0, column=0, sticky="ew", padx=(14, 8), pady=4)

        # Chevron Arrow
        self.lbl_arrow = ctk.CTkLabel(
            self,
            text="▾",
            font=ctk.CTkFont(family="Inter", size=13, weight="bold"),
            text_color="#818CF8"
        )
        self.lbl_arrow.grid(row=0, column=1, padx=(0, 14), pady=4)

        # Event Handlers
        for w in (self, self.lbl_text, self.lbl_arrow):
            w.bind("<Button-1>", self._on_toggle_click)
            w.bind("<Enter>", self._on_hover_enter)
            w.bind("<Leave>", self._on_hover_leave)

        self.bind("<Destroy>", self._on_destroy)

    def _on_hover_enter(self, event=None):
        if not (self.popup and self.popup.winfo_exists()):
            self.configure(border_color=THEME["accent_indigo"], fg_color="#121424")

    def _on_hover_leave(self, event=None):
        if not (self.popup and self.popup.winfo_exists()):
            self.configure(border_color=THEME["border_light"], fg_color="#0D0E1A")

    def _on_toggle_click(self, event=None):
        if self.popup and self.popup.winfo_exists():
            self.close_popup()
        else:
            self.open_popup()

    def open_popup(self):
        self.close_popup()
        try:
            root = self.winfo_toplevel()
        except Exception:
            return

        # Ambil koordinat absolut
        self.update_idletasks()
        rx = self.winfo_rootx()
        ry = self.winfo_rooty() + self.winfo_height() + 4
        rw = max(self.winfo_width(), 160)

        item_height = 32
        pop_height = len(self.values) * item_height + 12

        self.popup = ctk.CTkToplevel(root)
        self.popup.overrideredirect(True)
        self.popup.attributes("-topmost", True)
        self.popup.geometry(f"{rw}x{pop_height}+{rx}+{ry}")

        pop_frame = ctk.CTkFrame(
            self.popup,
            fg_color="#101222",
            border_width=1,
            border_color=THEME["border_light"],
            corner_radius=8
        )
        pop_frame.pack(fill="both", expand=True)

        for val in self.values:
            is_active = (val == self._current_value)
            
            # Baris item
            row_btn = ctk.CTkButton(
                pop_frame,
                text=f"  {val}" + ("          ✓" if is_active else ""),
                anchor="w",
                height=28,
                corner_radius=6,
                fg_color="#1E1B4B" if is_active else "transparent",
                hover_color="#1E2034",
                text_color="#818CF8" if is_active else THEME["text_body"],
                font=ctk.CTkFont(family="Inter", size=11, weight="bold" if is_active else "normal"),
                command=lambda v=val: self.select_value(v)
            )
            row_btn.pack(fill="x", padx=6, pady=2)

        self.configure(border_color=THEME["accent_indigo"], fg_color="#121424")
        self.lbl_arrow.configure(text="▴")

        # Global event listeners untuk auto-close saat klik di luar
        self._bind_click_id = root.bind("<Button-1>", self._on_root_click, add="+")
        self._bind_scroll_id = root.bind("<MouseWheel>", lambda e: self.close_popup(), add="+")
        self._bind_cfg_id = root.bind("<Configure>", lambda e: self.close_popup(), add="+")
        self._bind_esc_id = root.bind("<Escape>", lambda e: self.close_popup(), add="+")

    def _on_root_click(self, event):
        if not self.popup or not self.popup.winfo_exists():
            return
        x, y = event.x_root, event.y_root
        try:
            px, py = self.popup.winfo_rootx(), self.popup.winfo_rooty()
            pw, ph = self.popup.winfo_width(), self.popup.winfo_height()
            sx, sy = self.winfo_rootx(), self.winfo_rooty()
            sw, sh = self.winfo_width(), self.winfo_height()

            # Jangan tutup jika klik di area dropdown atau popup
            if (px <= x <= px + pw and py <= y <= py + ph) or (sx <= x <= sx + sw and sy <= y <= sy + sh):
                return
        except Exception:
            pass
        self.close_popup()

    def select_value(self, val: str):
        self._current_value = val
        self.lbl_text.configure(text=val)
        self.close_popup()
        if self.command:
            try:
                self.command(val)
            except Exception as e:
                print(f"Dropdown callback error: {e}")

    def close_popup(self):
        if self.popup and self.popup.winfo_exists():
            try:
                self.popup.destroy()
            except Exception:
                pass
            self.popup = None
        self.configure(border_color=THEME["border_light"], fg_color="#0D0E1A")
        self.lbl_arrow.configure(text="▾")

    def get(self) -> str:
        return self._current_value

    def set(self, val: str):
        self._current_value = val
        self.lbl_text.configure(text=val)

    def _on_destroy(self, event=None):
        self.close_popup()
