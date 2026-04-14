import customtkinter as ctk
import tkinter as tk
from tkinter import ttk
from tkinter import simpledialog, messagebox
from typing import List
from werkzeug.security import generate_password_hash
from sqlalchemy import delete, insert
from . import theme as theme_mod
from authz import has_role

try:
    # Package import (src.ui.admin -> src.db)
    from ..db import get_session, User, Role, user_roles
except Exception:
    # Top-level import when src is on sys.path (ui.admin -> db)
    from db import get_session, User, Role, user_roles


class AdminFrame(ctk.CTkFrame):
    """Simple admin panel for managing users and roles."""

    def __init__(self, master, dashboard=None):
        super().__init__(master, fg_color="transparent")
        self.dashboard = dashboard
        self._surface = theme_mod.SIMPLE_PALETTE.get("card", "#0f1724")
        self._surface_alt = "#0b1220"
        self._text_primary = "#e2e8f0"
        self._text_muted = "#94a3b8"
        self._accent = theme_mod.SIMPLE_PALETTE.get("primary", "#06B6D4")
        self._is_admin = bool(has_role(getattr(self.dashboard, "user", None), "admin")) if self.dashboard is not None else True
        if not self._is_admin:
            self._build_access_denied()
            return
        self._build_ui()
        self._load_users()
        self._load_roles()

    def _build_access_denied(self) -> None:
        frame = ctk.CTkFrame(self, fg_color=self._surface, corner_radius=14)
        frame.pack(fill="both", expand=True, padx=12, pady=12)
        ctk.CTkLabel(frame, text="Admin Access Required", font=("Segoe UI Semibold", 22), text_color=self._text_primary).pack(anchor="w", padx=14, pady=(14, 6))
        ctk.CTkLabel(
            frame,
            text="Only administrators can manage users, roles, and permissions.",
            font=("Segoe UI", 13),
            text_color=self._text_muted,
            wraplength=640,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 14))

    def _build_ui(self) -> None:
        header = ctk.CTkFrame(self, fg_color=self._surface, corner_radius=14)
        header.pack(fill="x", padx=12, pady=(12, 8))
        ctk.CTkLabel(header, text="Admin", font=("Segoe UI Semibold", 20), text_color=self._text_primary).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(header, text="Manage users, roles, and permissions", font=("Segoe UI", 12), text_color=self._text_muted).pack(anchor="w", padx=12, pady=(0, 10))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        left = ctk.CTkFrame(body, fg_color=self._surface, corner_radius=14)
        right = ctk.CTkFrame(body, fg_color=self._surface, corner_radius=14)
        left.pack(side='left', fill='both', expand=True, padx=12, pady=12)
        right.pack(side='left', fill='both', expand=True, padx=12, pady=12)

        lbl = ctk.CTkLabel(left, text="Users", font=("Segoe UI Semibold", 16), text_color=self._text_primary)
        lbl.pack(anchor='w', padx=10, pady=(10, 4))

        self.user_list = tk.Listbox(
            left,
            height=20,
            font=("Segoe UI", 13),
            bg=self._surface_alt,
            fg=self._text_primary,
            selectbackground=self._accent,
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self.user_list.pack(fill='both', expand=True, pady=(6, 8), padx=10)
        self.user_list.bind('<<ListboxSelect>>', lambda e: self._on_user_select())

        self.selected_user_label = ctk.CTkLabel(left, text="Selected user: None", font=("Segoe UI", 12), text_color=self._text_muted)
        self.selected_user_label.pack(anchor='w', pady=(0, 8), padx=10)

        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.pack(fill='x', padx=10, pady=(0, 10))
        btn_font = ("Segoe UI Semibold", 13)
        ctk.CTkButton(btns, text="Add User", command=self._open_create_user, width=102, height=34, font=btn_font, fg_color=self._accent, hover_color="#0891b2").pack(side='left', padx=4)
        ctk.CTkButton(btns, text="Edit User", command=self._edit_user, width=102, height=34, font=btn_font, fg_color="#334155", hover_color="#475569").pack(side='left', padx=4)
        ctk.CTkButton(btns, text="Reset Password", command=self._reset_password, width=138, height=34, font=btn_font, fg_color="#0f766e", hover_color="#115e59").pack(side='left', padx=4)
        ctk.CTkButton(btns, text="Delete User", command=self._delete_user, width=108, height=34, font=btn_font, fg_color="#b91c1c", hover_color="#991b1b").pack(side='left', padx=4)
        ctk.CTkButton(btns, text="Refresh", command=self._refresh_data, width=94, height=34, font=btn_font, fg_color="#334155", hover_color="#475569").pack(side='left', padx=4)

        lblr = ctk.CTkLabel(right, text="Roles", font=("Segoe UI Semibold", 16), text_color=self._text_primary)
        lblr.pack(anchor='w', padx=10, pady=(10, 4))
        self.roles_frame = ctk.CTkFrame(right, fg_color=self._surface_alt, corner_radius=10)
        self.roles_frame.pack(fill='both', expand=True, pady=(6, 8), padx=10)

        role_btns = ctk.CTkFrame(right, fg_color="transparent")
        role_btns.pack(fill='x', padx=10)
        ctk.CTkButton(role_btns, text="Add Role", command=self._open_create_role, width=102, height=34, font=btn_font, fg_color=self._accent, hover_color="#0891b2").pack(side='left', padx=6, pady=8)
        ctk.CTkButton(role_btns, text="Delete Role", command=self._delete_role, width=110, height=34, font=btn_font, fg_color="#b91c1c", hover_color="#991b1b").pack(side='left', padx=6, pady=8)

        # Save assignments
        save_frame = ctk.CTkFrame(right, fg_color="transparent")
        save_frame.pack(fill='x', pady=(8, 0), padx=10)
        ctk.CTkButton(save_frame, text="Save Assignments", command=self._save_role_assignments, width=168, height=34, font=btn_font, fg_color="#059669", hover_color="#047857").pack(side='left')

        # internal
        self._roles_check_vars = {}
        self._roles_order: List[Role] = []
        self._selected_user_id = None

    def _refresh_data(self) -> None:
        self._load_users()
        self._load_roles()
        self._selected_user_id = None
        try:
            self.selected_user_label.configure(text="Selected user: None")
        except Exception:
            pass

    def _get_selected_user(self):
        sel = self.user_list.curselection()
        if not sel:
            return None
        idx = sel[0]
        sess = get_session()
        try:
            users = sess.query(User).order_by(User.username).all()
            if idx >= len(users):
                return None
            return users[idx]
        finally:
            sess.close()

    def _load_users(self) -> None:
        try:
            sess = get_session()
            users = sess.query(User).order_by(User.username).all()
            self.user_list.delete(0, 'end')
            for u in users:
                display = f"{u.username} ({u.display_name or ''})"
                self.user_list.insert('end', display)
            sess.close()
        except Exception:
            messagebox.showerror('Error', 'Failed to load users')

    def _load_roles(self) -> None:
        try:
            sess = get_session()
            roles = sess.query(Role).order_by(Role.name).all()
            # clear frame
            for w in self.roles_frame.winfo_children():
                w.destroy()
            self._roles_check_vars = {}
            self._roles_order = roles
            for r in roles:
                var = tk.BooleanVar(value=False)
                cb = ctk.CTkCheckBox(self.roles_frame, text=r.name, variable=var, text_color=self._text_primary, font=("Segoe UI", 13))
                cb.pack(anchor='w', pady=4, padx=10)
                self._roles_check_vars[r.id] = var
            sess.close()
        except Exception:
            messagebox.showerror('Error', 'Failed to load roles')

    def _on_user_select(self) -> None:
        try:
            sel = self.user_list.curselection()
            if not sel:
                self._selected_user_id = None
                for v in self._roles_check_vars.values():
                    v.set(False)
                return
            idx = sel[0]
            # map idx to user id by re-querying ordered list
            sess = get_session()
            users = sess.query(User).order_by(User.username).all()
            if idx >= len(users):
                sess.close()
                return
            user = users[idx]
            self._selected_user_id = user.id
            try:
                self.selected_user_label.configure(text=f"Selected user: {user.username}")
            except Exception:
                pass
            # load assignments
            # build set of role_ids
            assigned = set()
            try:
                rlinks = sess.execute(user_roles.select().where(user_roles.c.user_id == user.id)).all()
                for row in rlinks:
                    assigned.add(row.role_id)
            except Exception:
                assigned = set()
            for rid, var in self._roles_check_vars.items():
                var.set(rid in assigned)
            sess.close()
        except Exception:
            messagebox.showerror('Error', 'Failed to select user')

    def _edit_user(self) -> None:
        try:
            user = self._get_selected_user()
            if not user:
                messagebox.showinfo('Info', 'Select a user first')
                return

            new_username = simpledialog.askstring(
                'Edit user',
                'Username:',
                initialvalue=user.username
            )
            if not new_username:
                return

            new_display = simpledialog.askstring(
                'Edit user',
                'Display name (optional):',
                initialvalue=user.display_name or ''
            )
            if new_display is None:
                return

            new_email = simpledialog.askstring(
                'Edit user',
                'Email (optional):',
                initialvalue=user.email or ''
            )
            if new_email is None:
                return

            sess = get_session()
            try:
                db_user = sess.query(User).filter(User.id == user.id).first()
                if not db_user:
                    messagebox.showerror('Error', 'User not found')
                    return

                # Ensure username uniqueness.
                existing = sess.query(User).filter(User.username == new_username.strip(), User.id != user.id).first()
                if existing:
                    messagebox.showerror('Error', 'Username already exists')
                    return

                db_user.username = new_username.strip()
                db_user.display_name = (new_display or '').strip()
                db_user.email = (new_email or '').strip() or None
                sess.commit()
                messagebox.showinfo('Saved', 'User updated')
            except Exception:
                sess.rollback()
                messagebox.showerror('Error', 'Failed to update user')
            finally:
                sess.close()
            self._load_users()
        except Exception:
            messagebox.showerror('Error', 'Failed to edit user')

    def _reset_password(self) -> None:
        try:
            user = self._get_selected_user()
            if not user:
                messagebox.showinfo('Info', 'Select a user first')
                return

            pwd1 = simpledialog.askstring('Reset password', f'New password for {user.username}:', show='*')
            if pwd1 is None:
                return
            pwd2 = simpledialog.askstring('Reset password', 'Confirm new password:', show='*')
            if pwd2 is None:
                return

            if pwd1 != pwd2:
                messagebox.showerror('Error', 'Passwords do not match')
                return
            if len(pwd1) < 4:
                messagebox.showerror('Error', 'Password must be at least 4 characters')
                return

            sess = get_session()
            try:
                db_user = sess.query(User).filter(User.id == user.id).first()
                if not db_user:
                    messagebox.showerror('Error', 'User not found')
                    return
                db_user.hashed_password = generate_password_hash(pwd1)
                sess.commit()
                messagebox.showinfo('Saved', 'Password reset successfully')
            except Exception:
                sess.rollback()
                messagebox.showerror('Error', 'Failed to reset password')
            finally:
                sess.close()
        except Exception:
            messagebox.showerror('Error', 'Failed to reset password')

    def _open_create_user(self) -> None:
        username = simpledialog.askstring('Create user', 'Username:')
        if not username:
            return
        display = simpledialog.askstring('Create user', 'Display name (optional):') or ''
        email = simpledialog.askstring('Create user', 'Email (optional):') or ''
        pwd = simpledialog.askstring('Create user', 'Password:', show='*')
        if pwd is None:
            return
        if len(pwd) < 4:
            messagebox.showerror('Error', 'Password must be at least 4 characters')
            return
        try:
            sess = get_session()
            existing = sess.query(User).filter(User.username == username.strip()).first()
            if existing:
                sess.close()
                messagebox.showerror('Error', 'Username already exists')
                return
            u = User(
                username=username.strip(),
                display_name=display.strip(),
                email=(email.strip() or None),
                hashed_password=generate_password_hash(pwd),
            )
            sess.add(u)
            sess.commit()
            sess.close()
            self._refresh_data()
            messagebox.showinfo('Saved', 'User created')
        except Exception:
            messagebox.showerror('Error', 'Failed to create user')

    def _open_create_role(self) -> None:
        name = simpledialog.askstring('Create role', 'Role name (e.g. admin):')
        if not name:
            return
        try:
            sess = get_session()
            r = Role(name=name.strip())
            sess.add(r)
            sess.commit()
            sess.close()
            self._load_roles()
        except Exception:
            messagebox.showerror('Error', 'Failed to create role')

    def _delete_user(self) -> None:
        try:
            sel = self.user_list.curselection()
            if not sel:
                return
            idx = sel[0]
            sess = get_session()
            users = sess.query(User).order_by(User.username).all()
            user = users[idx]
            if not messagebox.askyesno('Confirm', f'Delete user {user.username}?'):
                sess.close()
                return
            # remove user_roles links
            try:
                sess.execute(delete(user_roles).where(user_roles.c.user_id == user.id))
            except Exception:
                pass
            try:
                sess.delete(user)
                sess.commit()
            except Exception:
                sess.rollback()
                messagebox.showerror('Error', 'Failed to delete user')
            finally:
                sess.close()
            self._refresh_data()
        except Exception:
            messagebox.showerror('Error', 'Failed to delete user')

    def _delete_role(self) -> None:
        try:
            # pick role by name from roles_order via dialog
            names = [r.name for r in self._roles_order]
            if not names:
                return
            choice = simpledialog.askstring('Delete role', f'Role name to delete (options: {", ".join(names)}):')
            if not choice:
                return
            sess = get_session()
            r = sess.query(Role).filter(Role.name == choice.strip()).first()
            if not r:
                sess.close()
                messagebox.showerror('Error', 'Role not found')
                return
            if not messagebox.askyesno('Confirm', f'Delete role {r.name}?'):
                sess.close()
                return
            # remove links
            try:
                sess.execute(delete(user_roles).where(user_roles.c.role_id == r.id))
            except Exception:
                pass
            try:
                sess.delete(r)
                sess.commit()
            except Exception:
                sess.rollback()
                messagebox.showerror('Error', 'Failed to delete role')
            finally:
                sess.close()
            self._refresh_data()
        except Exception:
            messagebox.showerror('Error', 'Failed to delete role')

    def _save_role_assignments(self) -> None:
        try:
            if not self._selected_user_id:
                messagebox.showinfo('Info', 'Select a user first')
                return
            sess = get_session()
            # clear existing
            sess.execute(delete(user_roles).where(user_roles.c.user_id == self._selected_user_id))
            # insert selected
            for r in self._roles_order:
                var = self._roles_check_vars.get(r.id)
                if var and var.get():
                    sess.execute(insert(user_roles).values(user_id=self._selected_user_id, role_id=r.id))
            sess.commit()
            sess.close()
            messagebox.showinfo('Saved', 'Role assignments saved')
        except Exception:
            messagebox.showerror('Error', 'Failed to save assignments')
