import customtkinter as ctk
import tkinter as tk
from pathlib import Path
import json
from datetime import datetime, timedelta, date

try:
    from ..app_paths import data_path
except Exception:
    from app_paths import data_path
from .theme import SIMPLE_PALETTE

PALETTE = SIMPLE_PALETTE

class SchedulerFrame(ctk.CTkFrame):
    """Simple preventive maintenance scheduler UI (scaffold)."""
    def __init__(self, master, dashboard=None):
        super().__init__(master, fg_color="transparent")
        self.dashboard = dashboard
        self._scheduler_running = False
        self._scheduler_after_id = None
        self._scheduler_interval_hours = 6
        self.data_path = data_path("maintenance_tasks.json")
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        self.tasks = []
        # templates for recurring tasks
        self.templates_path = data_path("task_templates.json")
        self.templates = []
        self._load()
        self._build()

    def _load(self):
        try:
            if self.data_path.exists():
                with open(self.data_path, 'r', encoding='utf-8') as f:
                    self.tasks = json.load(f) or []
            else:
                self.tasks = []
        except Exception:
            self.tasks = []
        # load templates
        try:
            if self.templates_path.exists():
                with open(self.templates_path, 'r', encoding='utf-8') as f:
                    self.templates = json.load(f) or []
            else:
                self.templates = []
        except Exception:
            self.templates = []

    def _save(self):
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2)
        except Exception:
            pass
        try:
            with open(self.templates_path, 'w', encoding='utf-8') as f:
                json.dump(self.templates, f, indent=2)
        except Exception:
            pass

    def _build(self):
        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.pack(fill="both", expand=True, padx=18, pady=18)

        header = ctk.CTkFrame(shell, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
        header.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            header,
            text="Preventive Maintenance Scheduler",
            font=("Segoe UI Semibold", 23),
            text_color="#f8fafc",
        ).pack(anchor="w", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            header,
            text="Manage recurring maintenance tasks, due work, and scheduler automation.",
            font=("Segoe UI", 13),
            text_color="#94a3b8",
        ).pack(anchor="w", padx=14, pady=(0, 10))

        frame = ctk.CTkFrame(shell, fg_color=PALETTE.get("card", "#0f172a"), corner_radius=14)
        frame.pack(fill="both", expand=True)

        self.lb = tk.Listbox(
            frame,
            height=12,
            font=("Segoe UI", 13),
            bg="#0b1220",
            fg="#e2e8f0",
            selectbackground="#1d4ed8",
            selectforeground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self.lb.pack(side="left", fill="both", expand=True, padx=(12, 8), pady=12)

        ctrl = ctk.CTkFrame(frame, fg_color="#0b1220", corner_radius=12)
        ctrl.pack(side="left", fill="y", padx=(0, 12), pady=12)

        btn_font = ("Segoe UI Semibold", 13)
        add = ctk.CTkButton(ctrl, text='Add', height=34, font=btn_font, fg_color=PALETTE.get("primary", "#2563eb"), hover_color="#1d4ed8", command=self._add_task)
        add.pack(fill="x", padx=10, pady=(10, 6))
        run = ctk.CTkButton(ctrl, text='Mark Completed', height=34, font=btn_font, fg_color="#059669", hover_color="#047857", command=self._mark_completed)
        run.pack(fill="x", padx=10, pady=6)
        due = ctk.CTkButton(ctrl, text='Show Due/Overdue', height=34, font=btn_font, fg_color="#7c3aed", hover_color="#6d28d9", command=self._show_due)
        due.pack(fill="x", padx=10, pady=6)

        gen = ctk.CTkButton(ctrl, text='Generate Tasks Now', height=34, font=btn_font, fg_color="#0f766e", hover_color="#115e59", command=self._generate_now)
        gen.pack(fill="x", padx=10, pady=6)

        templ_btn = ctk.CTkButton(ctrl, text='Templates', height=34, font=btn_font, fg_color="#334155", hover_color="#475569", command=self._open_templates)
        templ_btn.pack(fill="x", padx=10, pady=6)

        cal_btn = ctk.CTkButton(ctrl, text='Calendar View', height=34, font=btn_font, fg_color="#334155", hover_color="#475569", command=self._toggle_calendar)
        cal_btn.pack(fill="x", padx=10, pady=6)

        self._sched_btn = ctk.CTkButton(ctrl, text='Start Scheduler', height=34, font=btn_font, fg_color="#b45309", hover_color="#92400e", command=self._toggle_scheduler)
        self._sched_btn.pack(fill="x", padx=10, pady=(6, 10))

        self._refresh()

        # calendar widget (simple)
        self._calendar_visible = False
        self._calendar_text = tk.Text(
            shell,
            height=12,
            state='disabled',
            font=("Consolas", 12),
            bg="#0b1220",
            fg="#e2e8f0",
            insertbackground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )

    def _refresh(self):
        self.lb.delete(0, 'end')
        for t in self.tasks:
            status = t.get('status','pending')
            subj = t.get('subject','')
            due = t.get('scheduled_at') or ''
            self.lb.insert('end', f"[{status}] {subj} | {due}")
        # refresh calendar if visible
        if getattr(self, '_calendar_visible', False):
            self._render_calendar()

    def _add_task(self):
        top = ctk.CTkToplevel(self)
        top.title('Add Task')
        top.geometry("420x220")
        panel = ctk.CTkFrame(top, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
        panel.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(panel, text="Task Subject", font=("Segoe UI", 13)).pack(anchor="w", padx=12, pady=(12, 4))
        subj = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13))
        subj.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(panel, text="Scheduled At", font=("Segoe UI", 13)).pack(anchor="w", padx=12, pady=(4, 4))
        sched = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13))
        sched.insert(0, datetime.utcnow().isoformat())
        sched.pack(fill="x", padx=12, pady=(0, 10))

        def _save():
            t = {'subject': subj.get().strip(), 'scheduled_at': sched.get().strip(), 'status': 'pending'}
            self.tasks.append(t)
            self._save()
            self._refresh()
            try:
                top.destroy()
            except Exception:
                pass

        btn_frame = ctk.CTkFrame(panel, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(0, 12))
        btn = ctk.CTkButton(btn_frame, text='Save', width=100, height=34, font=("Segoe UI Semibold", 13), command=_save)
        btn.pack(side="left")

    def _mark_completed(self):
        sel = self.lb.curselection()
        if not sel:
            return
        idx = sel[0]
        try:
            self.tasks[idx]['status'] = 'completed'
            self.tasks[idx]['completed_at'] = datetime.utcnow().isoformat()
            self._save()
            self._refresh()
        except Exception:
            pass

    def _show_due(self):
        from datetime import datetime
        now = datetime.utcnow()
        due = []
        for t in self.tasks:
            sa = t.get('scheduled_at')
            try:
                d = datetime.fromisoformat(sa)
                if d <= now and t.get('status') != 'completed':
                    due.append(t)
            except Exception:
                pass
        if not due:
            tk.messagebox.showinfo('Due', 'No due or overdue tasks')
        else:
            txt = '\n'.join([f"{d.get('subject')} | {d.get('scheduled_at')}" for d in due])
            tk.messagebox.showwarning('Due Tasks', txt)

    def _generate_now(self):
        try:
            if self.dashboard and hasattr(self.dashboard, 'generate_hour_based_tasks'):
                # run in background to avoid UI freeze
                import threading
                threading.Thread(target=self.dashboard.generate_hour_based_tasks, daemon=True).start()
                # also generate from templates
                threading.Thread(target=self._generate_from_templates, daemon=True).start()
                tk.messagebox.showinfo('Generate', 'Task generation started')
            else:
                tk.messagebox.showwarning('Unavailable', 'Generate function not available')
        except Exception:
            tk.messagebox.showerror('Error', 'Failed to start task generation')

    def _generate_from_templates(self, horizon_days: int = 30, dedup_minutes: int = 60):
        """Generate scheduled tasks from templates into `self.tasks` for the next `horizon_days` days."""
        try:
            now = datetime.utcnow()
            horizon = now + timedelta(days=horizon_days)
            existing = self.tasks or []
            new = []
            for tpl in self.templates:
                try:
                    ttype = tpl.get('type')
                    start_txt = tpl.get('start')
                    start = None
                    if start_txt:
                        try:
                            start = datetime.fromisoformat(start_txt)
                        except Exception:
                            start = now
                    else:
                        start = now

                    # occurrences generation
                    occ = []
                    if ttype == 'hourly':
                        ival = float(tpl.get('interval_hours', 24))
                        cur = start
                        while cur <= horizon:
                            occ.append(cur)
                            cur = cur + timedelta(hours=ival)
                    elif ttype == 'daily':
                        every = int(tpl.get('every', 1))
                        cur = start.date()
                        while datetime.combine(cur, datetime.min.time()) <= horizon:
                            occ.append(datetime.combine(cur, datetime.min.time()))
                            cur = cur + timedelta(days=every)
                    elif ttype == 'weekly':
                        every = int(tpl.get('every', 1))
                        # weekday list optional
                        weekdays = tpl.get('weekdays') or []
                        cur = start.date()
                        while datetime.combine(cur, datetime.min.time()) <= horizon:
                            if not weekdays or cur.weekday() in weekdays:
                                occ.append(datetime.combine(cur, datetime.min.time()))
                            cur = cur + timedelta(days=1)
                    elif ttype == 'monthly':
                        # simple monthly on day-of-month
                        day = int(tpl.get('day', start.day))
                        cur = start.date()
                        while datetime.combine(cur, datetime.min.time()) <= horizon:
                            try:
                                candidate = date(cur.year, cur.month, day)
                                dt = datetime.combine(candidate, datetime.min.time())
                                if dt >= start and dt <= horizon:
                                    occ.append(dt)
                            except Exception:
                                pass
                            # advance month
                            ym = cur.month + 1
                            yy = cur.year + (ym - 1) // 12
                            mm = (ym - 1) % 12 + 1
                            cur = date(yy, mm, 1)
                    else:
                        # unsupported type - skip
                        continue

                    for dt in occ:
                        subj = tpl.get('subject') or tpl.get('name') or 'Scheduled Task'
                        scheduled_at = dt.isoformat()
                        # dedup detection
                        dup = False
                        for ex in existing + new:
                            try:
                                if ex.get('subject') == subj:
                                    ex_dt = ex.get('scheduled_at')
                                    if not ex_dt:
                                        continue
                                    try:
                                        ex_d = datetime.fromisoformat(ex_dt)
                                        if abs((ex_d - dt).total_seconds()) <= dedup_minutes * 60:
                                            dup = True
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                continue
                        if dup:
                            continue
                        task = {
                            'subject': subj,
                            'scheduled_at': scheduled_at,
                            'status': 'pending',
                            'template': tpl.get('id')
                        }
                        new.append(task)
                except Exception:
                    continue

            if new:
                self.tasks.extend(new)
                try:
                    self._save()
                except Exception:
                    pass
                try:
                    self._refresh()
                except Exception:
                    pass
        except Exception:
            pass

    def _open_templates(self):
        top = ctk.CTkToplevel(self)
        top.title('Task Templates')
        top.geometry('640x400')
        frame = ctk.CTkFrame(top, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
        frame.pack(fill='both', expand=True, padx=8, pady=8)

        listbox = tk.Listbox(
            frame,
            font=("Segoe UI", 13),
            bg="#0b1220",
            fg="#e2e8f0",
            selectbackground="#1d4ed8",
            selectforeground="#f8fafc",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        listbox.pack(side='left', fill='both', expand=True, padx=12, pady=12)

        ctrl = ctk.CTkFrame(frame, fg_color="#0b1220", corner_radius=12)
        ctrl.pack(side='left', fill='y', padx=(0, 12), pady=12)

        def _refresh_list():
            listbox.delete(0, 'end')
            for t in self.templates:
                listbox.insert('end', f"{t.get('id')} | {t.get('subject')} | {t.get('type')}")

        def _add_tpl():
            d = ctk.CTkToplevel(top)
            d.title('New Template')
            d.geometry("460x320")
            panel = ctk.CTkFrame(d, fg_color=PALETTE.get("card", "#111827"), corner_radius=14)
            panel.pack(fill="both", expand=True, padx=12, pady=12)
            name = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13), placeholder_text="Template name")
            name.pack(fill='x', padx=12, pady=(12, 6))
            subj = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13), placeholder_text="Subject")
            subj.pack(fill='x', padx=12, pady=6)
            ctk.CTkLabel(panel, text='Type (hourly/daily/weekly/monthly)', font=("Segoe UI", 13)).pack(anchor='w', padx=12, pady=(6, 2))
            ttype = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13))
            ttype.pack(fill='x', padx=12, pady=4)
            ctk.CTkLabel(panel, text='Interval / params (json) e.g. {"interval_hours":24}', font=("Segoe UI", 13)).pack(anchor='w', padx=12, pady=(6, 2))
            params = ctk.CTkEntry(panel, height=36, font=("Segoe UI", 13))
            params.pack(fill='x', padx=12, pady=4)

            def _save_tpl():
                try:
                    pid = f"tpl_{int(datetime.utcnow().timestamp())}"
                    ptxt = params.get().strip()
                    p = {}
                    if ptxt:
                        try:
                            p = json.loads(ptxt)
                        except Exception:
                            p = {}
                    tpl = {'id': pid, 'name': name.get().strip(), 'subject': subj.get().strip(), 'type': ttype.get().strip(), 'start': datetime.utcnow().isoformat()}
                    tpl.update(p)
                    self.templates.append(tpl)
                    self._save()
                    _refresh_list()
                    try:
                        d.destroy()
                    except Exception:
                        pass
                except Exception:
                    pass

            btn = ctk.CTkButton(panel, text='Save', height=34, font=("Segoe UI Semibold", 13), command=_save_tpl)
            btn.pack(padx=12, pady=12, anchor="w")

        def _delete_tpl():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            # Only admin may delete templates
            try:
                from authz import has_role
                user = getattr(self, 'dashboard', None) and getattr(self.dashboard, 'user', None)
                if not user or not has_role(user, 'admin'):
                    tk.messagebox.showerror('Permission denied', 'Only administrators may delete templates.')
                    return
            except Exception:
                tk.messagebox.showerror('Permission denied', 'Unable to verify permissions.')
                return
            try:
                self.templates.pop(idx)
                self._save()
                _refresh_list()
            except Exception:
                pass

        addb = ctk.CTkButton(ctrl, text='Add Template', height=34, font=("Segoe UI Semibold", 13), fg_color=PALETTE.get("primary", "#2563eb"), hover_color="#1d4ed8", command=_add_tpl)
        addb.pack(fill="x", padx=10, pady=(10, 6))
        delb = ctk.CTkButton(ctrl, text='Delete', height=34, font=("Segoe UI Semibold", 13), fg_color="#b91c1c", hover_color="#991b1b", command=_delete_tpl)
        delb.pack(fill="x", padx=10, pady=6)
        _refresh_list()

    def _toggle_calendar(self):
        self._calendar_visible = not getattr(self, '_calendar_visible', False)
        if self._calendar_visible:
            self._calendar_text.pack(fill='both', expand=True, padx=12, pady=6)
            self._render_calendar()
        else:
            try:
                self._calendar_text.pack_forget()
            except Exception:
                pass

    def _render_calendar(self):
        try:
            # group tasks by date
            groups = {}
            for t in self.tasks:
                sa = t.get('scheduled_at')
                try:
                    d = datetime.fromisoformat(sa)
                    key = d.date().isoformat()
                except Exception:
                    key = 'unknown'
                groups.setdefault(key, []).append(t)

            lines = []
            for k in sorted(groups.keys()):
                lines.append(f"=== {k} ===")
                for t in groups[k]:
                    lines.append(f"[{t.get('status')}] {t.get('subject')} @ {t.get('scheduled_at')}")
                lines.append('')

            self._calendar_text.configure(state='normal')
            self._calendar_text.delete('1.0', 'end')
            self._calendar_text.insert('1.0', '\n'.join(lines))
            self._calendar_text.configure(state='disabled')
        except Exception:
            pass

    def _toggle_scheduler(self):
        try:
            if not self._scheduler_running:
                # start scheduler
                self._scheduler_running = True
                self._sched_btn.configure(text='Stop Scheduler')
                # schedule first tick immediately
                self._schedule_tick()
            else:
                # stop scheduler
                self._scheduler_running = False
                self._sched_btn.configure(text='Start Scheduler')
                try:
                    if self._scheduler_after_id:
                        self.after_cancel(self._scheduler_after_id)
                        self._scheduler_after_id = None
                except Exception:
                    pass
        except Exception:
            pass

    def _schedule_tick(self):
        try:
            # run generation in background
            if self.dashboard and hasattr(self.dashboard, 'generate_hour_based_tasks'):
                import threading
                threading.Thread(target=self.dashboard.generate_hour_based_tasks, daemon=True).start()
            # schedule next tick
            if self._scheduler_running:
                ms = int(self._scheduler_interval_hours * 3600 * 1000)
                try:
                    self._scheduler_after_id = self.after(ms, self._schedule_tick)
                except Exception:
                    # fallback to shorter scheduling if after fails
                    self._scheduler_after_id = self.after(60 * 1000, self._schedule_tick)
        except Exception:
            pass
