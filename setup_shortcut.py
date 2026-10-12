"""
Skrypt tworzacy ikone ICO z logo.jpg i skrot na pulpicie.
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 1. Konwertuj logo.jpg -> logo.ico
print("Konwertuje logo.jpg na logo.ico...")
try:
    from PIL import Image
    img = Image.open(os.path.join(BASE_DIR, 'logo.jpg'))
    img = img.convert('RGBA')
    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(os.path.join(BASE_DIR, 'logo.ico'), format='ICO', sizes=icon_sizes)
    print("[OK] Ikona logo.ico zostala utworzona!")
except Exception as e:
    print(f"[BLAD] Nie udalo sie skonwertowac ikony: {e}")

# 2. Utworz skrot na pulpicie
print("Tworze skrot na pulpicie...")
try:
    import subprocess
    
    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
    shortcut_path = os.path.join(desktop, 'Journal Trade.lnk')
    target = os.path.join(BASE_DIR, 'start.bat')
    icon = os.path.join(BASE_DIR, 'logo.ico')
    working_dir = BASE_DIR
    
    ps_script = f'''
$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
$Shortcut.TargetPath = "{target}"
$Shortcut.WorkingDirectory = "{working_dir}"
$Shortcut.IconLocation = "{icon}"
$Shortcut.Description = "Journal Trade - Trading Journal"
$Shortcut.WindowStyle = 7
$Shortcut.Save()
'''
    
    subprocess.run(['powershell', '-Command', ps_script], check=True)
    print(f"[OK] Skrot 'Journal Trade' zostal utworzony na pulpicie!")
    print(f"  Sciezka: {shortcut_path}")

except Exception as e:
    print(f"[BLAD] Nie udalo sie utworzyc skrotu: {e}")

print()
print("Gotowe! Mozesz teraz uruchomic aplikacje klikajac ikone 'Journal Trade' na pulpicie.")
