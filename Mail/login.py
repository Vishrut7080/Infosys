import tkinter as tk
from tkinter import messagebox

def gui_login():
    USER_CREDENTIALS = {'admin':'1234', 'vis':'password'}
    
    def attempt_login():
        username = username_entry.get().strip()
        password = password_entry.get().strip()
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            messagebox.showinfo("Login", f"Welcome, {username}!")
            root.destroy()  # close login window
        else:
            messagebox.showerror("Login", "Invalid credentials")
    
    root = tk.Tk()
    root.title("Assistant Login")
    
    tk.Label(root, text="Username:").grid(row=0, column=0)
    tk.Label(root, text="Password:").grid(row=1, column=0)
    
    username_entry = tk.Entry(root)
    username_entry.grid(row=0, column=1)
    
    password_entry = tk.Entry(root, show="*")
    password_entry.grid(row=1, column=1)
    
    tk.Button(root, text="Login", command=attempt_login).grid(row=2, columnspan=2)
    
    root.mainloop()

__all__=['gui_login']