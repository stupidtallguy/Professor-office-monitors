"""
Professor's Office Monitor (Mesa-style) — Priority with Returning Researchers
----------------------------------------------------------------------------
Roles & Priority:
1) Returning Researchers (highest) — researchers who left to do a task and came back
2) New Researchers (arrived at the door)
3) TAs
4) Students

Rules:
- Only one person is in the office (critical section) at a time.
- If a Researcher enters, the professor gives a task; the Researcher *leaves* the office to do it (sleep),
  then returns. While they are away, TAs and Students can enter (with TA priority).
- If a returning Researcher and a new Researcher are both waiting, the returning Researcher has priority.

Implementation:
- Python threading.Condition (Mesa semantics) + Tkinter UI.
- Optional Windows 11 styling via `sv-ttk` (Light/Dark toggle). Install with: `pip install sv-ttk`.

Run:
  python professor_office_monitor.py

Tested with Python 3.10+. No external deps except optional `sv-ttk`.
"""

import threading
import time
import random
from collections import deque
from dataclasses import dataclass
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk

# Optional Windows 11 theme (Sun Valley for Tk)
try:
    import sv_ttk  # pip install sv-ttk
    SVTTK_AVAILABLE = True
except Exception:
    SVTTK_AVAILABLE = False

# ------------------------------ Monitor ------------------------------ #
class OfficeMonitor:
    """Mesa-style monitor using threading.Condition with multi-tier priority."""

    def __init__(self):
        self._cv = threading.Condition()
        self.occupied: bool = False
        self.current: tuple[str, str] | None = None  # (role, name)
        # Priority queues
        self.waiting_returning_researchers: deque[str] = deque()  # highest
        self.waiting_new_researchers: deque[str] = deque()
        self.waiting_tas: deque[str] = deque()
        self.waiting_students: deque[str] = deque()

    # ---------------------- Read-only state helpers ---------------------- #
    def snapshot(self):
        """Get a shallow copy of the state for the UI (no lock held by UI)."""
        with self._cv:
            return (
                self.occupied,
                None if self.current is None else tuple(self.current),
                list(self.waiting_returning_researchers),
                list(self.waiting_new_researchers),
                list(self.waiting_tas),
                list(self.waiting_students),
            )

    # ------------------------- Monitor operations ----------------------- #
    def enter(self, role: str, name: str, returning: bool = False):
        """Attempt to enter the office according to priority tiers.

        Queuing rules (on first call, enqueue; then wait in a while loop until at head & office free):
        - Returning Researcher -> waiting_returning_researchers
        - New Researcher -> waiting_new_researchers
        - TA -> waiting_tas
        - Student -> waiting_students
        """
        with self._cv:
            if role == "Researcher":
                if returning:
                    self.waiting_returning_researchers.append(name)
                else:
                    self.waiting_new_researchers.append(name)
            elif role == "TA":
                self.waiting_tas.append(name)
            else:
                self.waiting_students.append(name)

            while True:
                can_enter = False
                if not self.occupied:
                    # Evaluate priority tiers
                    if self.waiting_returning_researchers:
                        can_enter = (role == "Researcher" and returning and self.waiting_returning_researchers[0] == name)
                    elif self.waiting_new_researchers:
                        can_enter = (role == "Researcher" and not returning and self.waiting_new_researchers[0] == name)
                    elif self.waiting_tas:
                        can_enter = (role == "TA" and self.waiting_tas[0] == name)
                    elif self.waiting_students:
                        can_enter = (role == "Student" and self.waiting_students[0] == name)
                if can_enter:
                    self.occupied = True
                    self.current = (role, name)
                    if role == "Researcher":
                        if returning:
                            assert self.waiting_returning_researchers and self.waiting_returning_researchers[0] == name
                            self.waiting_returning_researchers.popleft()
                        else:
                            assert self.waiting_new_researchers and self.waiting_new_researchers[0] == name
                            self.waiting_new_researchers.popleft()
                    elif role == "TA":
                        assert self.waiting_tas and self.waiting_tas[0] == name
                        self.waiting_tas.popleft()
                    else:
                        assert self.waiting_students and self.waiting_students[0] == name
                        self.waiting_students.popleft()
                    return
                self._cv.wait()

    def leave(self):
        with self._cv:
            self.occupied = False
            self.current = None
            self._cv.notify_all()


# ------------------------------ Visitor ------------------------------ #
@dataclass
class Visitor:
    role: str  # "Researcher" | "TA" | "Student"
    name: str


class Simulator:
    """Spawns and manages visitor threads, relaying events to the UI."""

    def __init__(self, monitor: OfficeMonitor, event_bus: Queue):
        self.monitor = monitor
        self.event_bus = event_bus
        self._id_counters = {"Researcher": 0, "TA": 0, "Student": 0}
        self._stop_auto = threading.Event()
        self._threads: list[threading.Thread] = []

    def _next_name(self, role: str) -> str:
        self._id_counters[role] += 1
        prefix = {"Researcher": "R", "TA": "TA", "Student": "S"}[role]
        return f"{prefix}-{self._id_counters[role]:02d}"

    def add_visitor(self, role: str):
        name = self._next_name(role)
        v = Visitor(role, name)
        t = threading.Thread(target=self._run_visitor, args=(v,), daemon=True)
        t.start()
        self._threads.append(t)
        self.event_bus.put(("spawn", v.role, v.name))

    def _run_visitor(self, v: Visitor):
        self.event_bus.put(("arrive", v.role, v.name))
        if v.role == "Researcher":
            # Stage 1: Consult & get task
            self.monitor.enter(v.role, v.name, returning=False)
            self.event_bus.put(("enter", v.role, v.name))
            time.sleep(random.uniform(1.0, 1.8))  # short consult to receive task
            self.monitor.leave()
            self.event_bus.put(("task_start", v.role, v.name))
            # Work on task outside office
            time.sleep(random.uniform(2.0, 3.5))
            self.event_bus.put(("wake", v.role, v.name))
            # Stage 2: Return with priority for returning researchers
            self.monitor.enter(v.role, v.name, returning=True)
            self.event_bus.put(("enter", v.role, v.name))
            time.sleep(random.uniform(0.8, 1.5))  # deliver results / finalize
            self.monitor.leave()
            self.event_bus.put(("leave", v.role, v.name))
        else:
            # TA or Student: simple enter/leave
            self.monitor.enter(v.role, v.name)
            self.event_bus.put(("enter", v.role, v.name))
            time.sleep(random.uniform(1.2, 2.2))
            self.monitor.leave()
            self.event_bus.put(("leave", v.role, v.name))

    # ------------------------- Auto-arrival loop ------------------------- #
    def start_auto(self):
        if self._stop_auto.is_set():
            self._stop_auto.clear()
        th = threading.Thread(target=self._auto_loop, daemon=True)
        th.start()
        self._threads.append(th)

    def stop_auto(self):
        self._stop_auto.set()

    def _auto_loop(self):
        while not self._stop_auto.is_set():
            # Mix of arrivals; researchers less frequent but high priority when returning
            r = random.random()
            if r < 0.25:
                role = "Researcher"
            elif r < 0.55:
                role = "TA"
            else:
                role = "Student"
            self.add_visitor(role)
            time.sleep(random.uniform(0.7, 1.7))


# ------------------------------- The UI ------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Professor's Office — Monitor with Returning Researcher Priority")
        self.geometry("1320x720")
        self.minsize(1200, 680)
        self.resizable(True, True)

        # Apply Windows 11-like theme if available
        if SVTTK_AVAILABLE:
            sv_ttk.set_theme("light")
            try:
                self.tk.call("tk", "scaling", 1.2)
            except Exception:
                pass

        # Model
        self.monitor = OfficeMonitor()
        self.event_bus: Queue = Queue()
        self.sim = Simulator(self.monitor, self.event_bus)

        # Layout: four columns (queues), center office, right controls/log
        # Set column weights and minimum widths for better sizing
        self.columnconfigure(0, weight=1, minsize=260, uniform="cols")
        self.columnconfigure(1, weight=1, minsize=260, uniform="cols")
        self.columnconfigure(2, weight=1, minsize=320, uniform="cols")
        self.columnconfigure(3, weight=1, minsize=260, uniform="cols")
        self.columnconfigure(4, weight=1, minsize=320)

        # Queues area
        self._build_queues()

        # Center: office
        center = ttk.Frame(self, padding=12)
        center.grid(row=0, column=2, sticky="nsew")
        ttk.Label(center, text="Office (Critical Section)", font=("Helvetica", 14, "bold"), wraplength=280, justify="center").pack()
        self.office_card = ttk.Frame(center, padding=16, relief="ridge")
        # Fix card size and prevent geometry shrink
        self.office_card.pack(fill="both", expand=True, pady=8)
        self.office_card.update_idletasks()
        self.office_card.configure(width=300, height=360)
        self.office_card.pack_propagate(False)
        self.occupant_var = tk.StringVar(value="Empty")
        ttk.Label(self.office_card, textvariable=self.occupant_var, font=("Helvetica", 16, "bold")).pack(pady=16)
        self.status_var = tk.StringVar(value="—")
        ttk.Label(self.office_card, textvariable=self.status_var).pack()

        # Right: controls & event log
        right = ttk.Frame(self, padding=12)
        right.grid(row=0, column=4, sticky="nsew")
        ttk.Label(right, text="Controls", font=("Helvetica", 12, "bold")).pack(anchor="w")
        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=(6, 12))
        ttk.Button(btns, text="Add Researcher", command=lambda: self.sim.add_visitor("Researcher")).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Add TA", command=lambda: self.sim.add_visitor("TA")).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Add Student", command=lambda: self.sim.add_visitor("Student")).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Auto Arrivals ▶", command=self.sim.start_auto).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Stop Auto ⏸", command=self.sim.stop_auto).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Reset", command=self.reset).grid(row=1, column=2, padx=4, pady=4, sticky="ew")

        ttk.Label(right, text="Appearance", font=("Helvetica", 11, "bold")).pack(anchor="w", pady=(6, 2))
        theme_row = ttk.Frame(right)
        theme_row.pack(fill="x", pady=(0, 10))
        ttk.Button(theme_row, text="Light", command=lambda: self._set_theme("light")).grid(row=0, column=0, padx=4, sticky="ew")
        ttk.Button(theme_row, text="Dark", command=lambda: self._set_theme("dark")).grid(row=0, column=1, padx=4, sticky="ew")

        ttk.Label(right, text="Event Log", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(8, 0))
        log_wrap = ttk.Frame(right)
        log_wrap.pack(fill="both", expand=True)
        self.log = tk.Text(log_wrap, height=20, width=50, wrap="word", state="disabled")
        yscroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=yscroll.set)
        self.log.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        log_wrap.columnconfigure(0, weight=1)
        log_wrap.rowconfigure(0, weight=1)

        # Event loop
        self.after(100, self._drain_events)
        self.after(150, self._refresh_state)

    # --------------------------- Build Queues --------------------------- #
    def _build_queues(self):
        # Column 0: Returning Researchers
        col0 = ttk.Frame(self, padding=12)
        col0.grid(row=0, column=0, sticky="nsew")
        ttk.Label(col0, text="Returning Researchers", font=("Helvetica", 12, "bold"), wraplength=230, justify="left").pack(anchor="w")
        self.rr_list = self._new_listbox(col0, height=14)

        # Column 1: New Researchers
        col1 = ttk.Frame(self, padding=12)
        col1.grid(row=0, column=1, sticky="nsew")
        ttk.Label(col1, text="Researchers (new)", font=("Helvetica", 12, "bold"), wraplength=230, justify="left").pack(anchor="w")
        self.rn_list = self._new_listbox(col1, height=14)

        # Column 3 (left of controls): TAs & Students stacked
        col3 = ttk.Frame(self, padding=12)
        col3.grid(row=0, column=3, sticky="nsew")
        ttk.Label(col3, text="Waiting — TAs", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.ta_list = self._new_listbox(col3, height=8)
        ttk.Label(col3, text="Waiting — Students", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.stu_list = self._new_listbox(col3, height=10)

    def _new_listbox(self, parent: ttk.Frame, height: int = 10) -> tk.Listbox:
        wrap = ttk.Frame(parent)
        wrap.pack(fill="both", expand=False, pady=(4, 12))
        lb = tk.Listbox(wrap, height=height, width=28)
        yscroll = ttk.Scrollbar(wrap, orient="vertical", command=lb.yview)
        lb.configure(yscrollcommand=yscroll.set)
        lb.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        wrap.columnconfigure(0, weight=1)
        return lb

    def reset(self):
        self.sim.stop_auto()
        for lb in (self.rr_list, self.rn_list, self.ta_list, self.stu_list):
            lb.delete(0, tk.END)
        self._set_office("Empty", "—")
        self._log("— Reset UI. New arrivals will continue to obey priority.")

    def _set_office(self, title: str, status: str):
        self.occupant_var.set(title)
        self.status_var.set(status)

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + msg + "")
        self.log.configure(state="disabled")
        self.log.see("end")

    def _set_theme(self, mode: str):
        if SVTTK_AVAILABLE:
            sv_ttk.set_theme(mode)
            self._log(f"Switched to {mode} theme (Windows 11 style)")
        else:
            self._log("Windows 11 theme not available — install 'sv-ttk' to enable.")

    # --------------------------- Event handling ------------------------- #
    def _drain_events(self):
        try:
            while True:
                kind, role, name = self.event_bus.get_nowait()
                if kind == "spawn":
                    self._log(f"Spawned {role} {name}")
                elif kind == "arrive":
                    if role == "Researcher":
                        self.rn_list.insert("end", name)
                    elif role == "TA":
                        self.ta_list.insert("end", name)
                    else:
                        self.stu_list.insert("end", name)
                    self._log(f"{role} {name} arrived and queued")
                elif kind == "enter":
                    self._set_office(f"In office: {role} {name}", "Consultation in progress…")
                    # Ensure removal from any visible list
                    self._remove_from_lists(name)
                    self._log(f"{role} {name} ENTERED the office")
                elif kind == "task_start":
                    self._set_office("Empty", "—")
                    # Move researcher from new list to returning list visually
                    self._remove_from_lists(name)
                    self.rr_list.insert("end", name)
                    self._log(f"Researcher {name} left to do a task (will return with highest priority)")
                elif kind == "wake":
                    # Already shown in RR list; keep log for clarity
                    self._log(f"Researcher {name} finished task and is waiting to re-enter (returning)")
                elif kind == "leave":
                    self._set_office("Empty", "—")
                    self._log(f"{role} {name} left the office")
        except Empty:
            pass
        finally:
            self.after(80, self._drain_events)

    def _remove_from_lists(self, name: str):
        for lb in (self.rr_list, self.rn_list, self.ta_list, self.stu_list):
            try:
                idx = lb.get(0, "end").index(name)
                lb.delete(idx)
            except ValueError:
                continue

    # ------------------------- Periodic refresh ------------------------- #
    def _refresh_state(self):
        occupied, current, rr, rn, tas, students = self.monitor.snapshot()

        # Sync waiting lists with monitor state
        self._sync_listbox(self.rr_list, rr)
        self._sync_listbox(self.rn_list, rn)
        self._sync_listbox(self.ta_list, tas)
        self._sync_listbox(self.stu_list, students)

        # Sync office occupant label if needed
        if not occupied:
            if self.occupant_var.get() != "Empty":
                self._set_office("Empty", "—")
        else:
            role, name = current
            label = f"In office: {role} {name}"
            if self.occupant_var.get() != label:
                self._set_office(label, "Consultation in progress…")

        self.after(250, self._refresh_state)

    @staticmethod
    def _sync_listbox(lb: tk.Listbox, items: list[str]):
        current = list(lb.get(0, "end"))
        if current != items:
            lb.delete(0, tk.END)
            for it in items:
                lb.insert("end", it)


# ------------------------------- Startup ------------------------------ #
if __name__ == "__main__":
    random.seed()
    app = App()
    app.mainloop()
