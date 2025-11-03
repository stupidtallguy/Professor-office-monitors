"""
Professor's Office Monitor (Mesa-style) with TA Priority — Tkinter UI
--------------------------------------------------------------------
- Only one person (TA or Student) may be in the office at a time (critical section).
- Waiting queue gives **priority to TAs** over Students.
- Implemented using Python's threading.Condition (Mesa semantics: signaler keeps control; waiters re-check conditions).
- Includes a simple Tkinter UI to visualize queues and occupancy, with buttons to spawn visitors.

"""

import threading
import time
import random
from collections import deque
from dataclasses import dataclass
from queue import Queue, Empty
import tkinter as tk
from tkinter import ttk

# ------------------------------ Monitor ------------------------------ #
class OfficeMonitor:
    """Mesa-style monitor using threading.Condition, with TA priority."""

    def __init__(self):
        self._cv = threading.Condition()
        self.occupied: bool = False
        self.current: tuple[str, str] | None = None  # (role, name)
        self.waiting_tas: deque[str] = deque()
        self.waiting_students: deque[str] = deque()

    # ---------------------- Read-only state helpers ---------------------- #
    def snapshot(self):
        """Get a shallow copy of the state for the UI (no lock held by UI)."""
        with self._cv:
            return (
                self.occupied,
                None if self.current is None else tuple(self.current),
                list(self.waiting_tas),
                list(self.waiting_students),
            )

    # ------------------------- Monitor operations ----------------------- #
    def enter(self, role: str, name: str):
        """
        Enter the office. Respect TA priority.
        - TAs: join TA queue; wait until office is free and they're at head of TA queue.
        - Students: join Student queue; wait until office is free, no TAs are waiting, and they're at head of Student queue.
        """
        with self._cv:
            if role == "TA":
                self.waiting_tas.append(name)
            else:
                self.waiting_students.append(name)

            # Mesa semantics: wait in a while loop, re-check predicate on wakeup
            while True:
                can_enter = False
                if not self.occupied:
                    if role == "TA":
                        can_enter = (len(self.waiting_tas) > 0 and self.waiting_tas[0] == name)
                    else:  # Student
                        # Students can enter only if: (a) at head of student queue, and (b) no TA waiting
                        can_enter = (
                            len(self.waiting_students) > 0 and self.waiting_students[0] == name and len(self.waiting_tas) == 0
                        )
                if can_enter:
                    # Occupy and remove from appropriate queue
                    self.occupied = True
                    self.current = (role, name)
                    if role == "TA":
                        assert self.waiting_tas and self.waiting_tas[0] == name
                        self.waiting_tas.popleft()
                    else:
                        assert self.waiting_students and self.waiting_students[0] == name
                        self.waiting_students.popleft()
                    return  # Entered critical section
                self._cv.wait()

    def leave(self):
        """Leave the office and notify all waiters (Mesa signal)."""
        with self._cv:
            self.occupied = False
            self.current = None
            # Wake everyone so the head of TA queue (if any) can enter, else head of student queue
            self._cv.notify_all()


# ------------------------------ Visitor ------------------------------ #
@dataclass
class Visitor:
    role: str  # "TA" or "Student"
    name: str


class Simulator:
    """Spawns and manages visitor threads, relaying events to the UI."""

    def __init__(self, monitor: OfficeMonitor, event_bus: Queue):
        self.monitor = monitor
        self.event_bus = event_bus
        self._id_counters = {"TA": 0, "Student": 0}
        self._stop_auto = threading.Event()
        self._threads: list[threading.Thread] = []

    def _next_name(self, role: str) -> str:
        self._id_counters[role] += 1
        prefix = "TA" if role == "TA" else "S"
        return f"{prefix}-{self._id_counters[role]:02d}"

    def add_visitor(self, role: str):
        name = self._next_name(role)
        v = Visitor(role, name)
        t = threading.Thread(target=self._run_visitor, args=(v,), daemon=True)
        t.start()
        self._threads.append(t)
        self.event_bus.put(("spawn", v.role, v.name))

    def _run_visitor(self, v: Visitor):
        # Arrive -> enter -> stay for some time -> leave
        self.event_bus.put(("arrive", v.role, v.name))
        self.monitor.enter(v.role, v.name)
        self.event_bus.put(("enter", v.role, v.name))
        # Simulate consultation time
        time.sleep(random.uniform(1.5, 3.0))
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
            # Bias slightly toward students for volume, but TAs keep priority at the door
            role = "TA" if random.random() < 0.35 else "Student"
            self.add_visitor(role)
            time.sleep(random.uniform(0.8, 1.8))


# ------------------------------- The UI ------------------------------- #
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Professor's Office — Monitor with TA Priority")
        self.geometry("880x520")
        self.resizable(False, False)

        # Model
        self.monitor = OfficeMonitor()
        self.event_bus: Queue = Queue()
        self.sim = Simulator(self.monitor, self.event_bus)

        # Styles
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Layout: left (queues), center (office), right (controls & log)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        # Left: queues
        left = ttk.Frame(self, padding=12)
        left.grid(row=0, column=0, sticky="nsew")
        ttk.Label(left, text="Waiting — TAs (priority)", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.ta_list = tk.Listbox(left, height=10)
        self.ta_list.pack(fill="x", pady=(4, 12))
        ttk.Label(left, text="Waiting — Students", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.stu_list = tk.Listbox(left, height=12)
        self.stu_list.pack(fill="x", pady=(4, 12))

        # Center: office status
        center = ttk.Frame(self, padding=12)
        center.grid(row=0, column=1, sticky="nsew")
        ttk.Label(center, text="Office (Critical Section)", font=("Helvetica", 14, "bold")).pack()
        self.office_card = ttk.Frame(center, padding=16, relief="ridge")
        self.office_card.pack(fill="both", expand=True, pady=8)
        self.occupant_var = tk.StringVar(value="Empty")
        ttk.Label(self.office_card, textvariable=self.occupant_var, font=("Helvetica", 16, "bold")).pack(pady=16)
        self.status_var = tk.StringVar(value="—")
        ttk.Label(self.office_card, textvariable=self.status_var).pack()

        # Right: controls & event log
        right = ttk.Frame(self, padding=12)
        right.grid(row=0, column=2, sticky="nsew")
        ttk.Label(right, text="Controls", font=("Helvetica", 12, "bold")).pack(anchor="w")
        btns = ttk.Frame(right)
        btns.pack(fill="x", pady=(6, 12))
        ttk.Button(btns, text="Add TA", command=lambda: self.sim.add_visitor("TA")).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Add Student", command=lambda: self.sim.add_visitor("Student")).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Auto Arrivals ▶", command=self.sim.start_auto).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Stop Auto ⏸", command=self.sim.stop_auto).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ttk.Button(btns, text="Reset", command=self.reset).grid(row=2, column=0, columnspan=2, padx=4, pady=4, sticky="ew")

        ttk.Label(right, text="Event Log", font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(8, 0))
        self.log = tk.Text(right, height=18, width=36, state="disabled")
        self.log.pack(fill="both", expand=True)

        # Kick off event processing & periodic UI refresh
        self.after(100, self._drain_events)
        self.after(150, self._refresh_state)

    # --------------------------- UI callbacks --------------------------- #
    def reset(self):
        # Not a hard reset for threads; stops auto and clears UI/state safely when quiescent
        self.sim.stop_auto()
        # There might still be active threads; we just clear visible queues, the monitor snapshot governs truth
        self.ta_list.delete(0, tk.END)
        self.stu_list.delete(0, tk.END)
        self._set_office("Empty", "—")
        self._log("— Reset UI. New arrivals will continue to obey priority.")

    def _set_office(self, title: str, status: str):
        self.occupant_var.set(title)
        self.status_var.set(status)

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", time.strftime("%H:%M:%S ") + msg + "\n")
        self.log.configure(state="disabled")
        self.log.see("end")

    # --------------------------- Event handling ------------------------- #
    def _drain_events(self):
        try:
            while True:
                kind, role, name = self.event_bus.get_nowait()
                if kind == "spawn":
                    self._log(f"Spawned {role} {name}")
                elif kind == "arrive":
                    # Add to waiting list immediately for visual responsiveness
                    if role == "TA":
                        self.ta_list.insert("end", name)
                    else:
                        self.stu_list.insert("end", name)
                    self._log(f"{role} {name} arrived and queued")
                elif kind == "enter":
                    self._set_office(f"In office: {role} {name}", "Consultation in progress…")
                    # Remove from lists if still present
                    self._remove_from_lists(name)
                    self._log(f"{role} {name} ENTERED the office")
                elif kind == "leave":
                    self._set_office("Empty", "—")
                    self._log(f"{role} {name} left the office")
        except Empty:
            pass
        finally:
            self.after(80, self._drain_events)

    def _remove_from_lists(self, name: str):
        for lb in (self.ta_list, self.stu_list):
            try:
                idx = lb.get(0, "end").index(name)
                lb.delete(idx)
            except ValueError:
                continue

    # ------------------------- Periodic refresh ------------------------- #
    def _refresh_state(self):
        # Cross-check UI with monitor snapshot to avoid drift
        occupied, current, tas, students = self.monitor.snapshot()

        # Sync waiting lists (cheap reconciliation)
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
