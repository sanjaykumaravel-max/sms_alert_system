import psutil
import sys

found = False
for p in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
    try:
        cmdline = p.info.get('cmdline') or []
        cmd = ' '.join(cmdline)
        if 'src/main.py' in cmd or 'src\\main.py' in cmd or cmd.endswith('src/main.py'):
            found = True
            pid = p.info['pid']
            print(f"Killing PID={pid} CMD={cmd}")
            p.kill()
    except Exception as e:
        # ignore processes that vanish
        pass

if not found:
    print('No matching process found')
