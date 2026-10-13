import os
import re

css_path = r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Website\assets\css\site.css"
if os.path.exists(css_path):
    with open(css_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Inject neon variables
    if "--glow-primary" not in content:
        content = content.replace(":root {", ":root {\n  --glow-primary: 0 0 10px #00f0ff, 0 0 20px #00f0ff;\n  --glow-accent: 0 0 10px #ff00ff, 0 0 20px #ff00ff;")
    
    # Overwrite colors to match the futuristic vibe
    content = re.sub(r"--bg-primary:.*?;", "--bg-primary: #050510;", content)
    content = re.sub(r"--bg-card:.*?;", "--bg-card: rgba(10, 15, 30, 0.7);", content)
    content = re.sub(r"--ink-primary:.*?;", "--ink-primary: #e0f7fa;", content)
    
    # Add box-shadow to buttons
    if "box-shadow: var(--glow-primary);" not in content:
        content = content.replace(".btn {", ".btn {\n  box-shadow: var(--glow-primary);\n  text-transform: uppercase;\n  letter-spacing: 1px;")
        
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated site.css")
else:
    print("site.css not found")

admin_css = r"E:\All Project\AutoMovie_Pro_SAAS_Final_Update\AutoMoviePro-Website\admin\_layout.php"
if os.path.exists(admin_css):
    with open(admin_css, "r", encoding="utf-8") as f:
        content = f.read()
    if "--glow-primary" not in content:
        content = content.replace(":root {", ":root {\n      --glow-primary: 0 0 10px #00f0ff, 0 0 20px #00f0ff;\n      --glow-accent: 0 0 10px #ff00ff, 0 0 20px #ff00ff;")
        content = re.sub(r"--bg-primary:.*?;", "--bg-primary: #050510;", content)
        content = re.sub(r"--bg-sidebar:.*?;", "--bg-sidebar: rgba(10, 15, 30, 0.9);", content)
        content = re.sub(r"--bg-card:.*?;", "--bg-card: rgba(10, 15, 30, 0.7);", content)
    with open(admin_css, "w", encoding="utf-8") as f:
        f.write(content)
    print("Updated admin layout CSS")
