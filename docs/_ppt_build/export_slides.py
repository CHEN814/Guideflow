from pathlib import Path

import win32com.client

pptx = Path(r"D:\Project\guideflow\code\docs\DLBCL评估方案.pptx").resolve()
out_dir = Path(r"D:\Project\guideflow\code\docs\_ppt_build\qa").resolve()
out_dir.mkdir(parents=True, exist_ok=True)

app = win32com.client.DispatchEx("PowerPoint.Application")
app.Visible = True
app.DisplayAlerts = 0
presentation = app.Presentations.Open(str(pptx), ReadOnly=True, WithWindow=False)
try:
    for i, slide in enumerate(presentation.Slides, 1):
        dest = out_dir / f"slide-{i:02d}.png"
        slide.Export(str(dest), "PNG", 1920, 1080)
        print("exported", dest.name)
finally:
    presentation.Close()
    app.Quit()
