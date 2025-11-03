🗂 Repository Structure
professor-office-monitors/
│
├── office_monitor_win11.html               # Web-based TA-priority monitor (async + JS UI)
├── PR.py                                   # Professor’s Office with Returning Researchers + Tkinter UI
├── professorOffice.py                      # TA-priority monitor in Python/Tkinter
├── ProfessorOffice_withResearcher.py       # Returning Researchers + multi-tier priority system
├── README.md

# Professor’s Office Monitors 🧑‍🏫💻

This repository contains multiple **synchronization and concurrency simulations** that visualize how access to a professor’s office is managed under different priority rules.  
They use **Mesa-style monitor semantics**, and each variant provides an interactive UI — either web-based (HTML/JS) or native (Tkinter).

---

## 🚀 Projects Included

### 1. 🪟 `office_monitor_win11.html` — Web TA Priority Monitor
A Fluent/Windows 11–styled **asynchronous JavaScript** simulation demonstrating:
- TA vs. Student priority (TA always preferred)
- Fair queuing logic implemented with custom `AsyncMutex` and `WaitSet`
- Dynamic UI showing office occupancy, waiting queues, and event logs
- Auto-arrival simulation for continuous visualization

**Run:**  
Open directly in a browser — no backend required.

---

### 2. 🧵 `professorOffice.py` — TA Priority Monitor (Python)
A Python **Tkinter** visualization of the same concept:
- Mesa-style monitor using `threading.Condition`
- TA priority logic with real threads and synchronized entry/exit
- GUI with live queues, event log, and auto-arrival controls

**Run:**  
```bash
python professorOffice.py
