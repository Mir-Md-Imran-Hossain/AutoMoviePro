import os
import re

app_css_path = r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Software\ui\static\css\app.css"

if os.path.exists(app_css_path):
    with open(app_css_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    content = re.sub(r"--bg0:.*?;", "--bg0: #050510;", content)
    content = re.sub(r"--bg1:.*?;", "--bg1: rgba(10, 15, 30, 0.7);", content)
    content = re.sub(r"--panel:.*?;", "--panel: rgba(20, 25, 40, 0.8);", content)
    content = re.sub(r"--brand:.*?;", "--brand: #00f0ff;", content)
    content = re.sub(r"--brand-deep:.*?;", "--brand-deep: #0077ff;", content)
    content = re.sub(r"--accent:.*?;", "--accent: #ff00ff;", content)
    content = re.sub(r"--line-strong:.*?;", "--line-strong: rgba(0, 240, 255, 0.6);", content)
    content = re.sub(r"--shadow:.*?;", "--shadow: 0 0 20px rgba(0, 240, 255, 0.2);", content)
    
    # Inject glow classes if not exists
    if "--glow-brand:" not in content:
        content = content.replace(":root {", ":root {\n  --glow-brand: 0 0 10px #00f0ff, 0 0 20px #00f0ff;\n  --glow-accent: 0 0 10px #ff00ff, 0 0 20px #ff00ff;")
        
    with open(app_css_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated app.css successfully.")
else:
    print("app.css not found.")
