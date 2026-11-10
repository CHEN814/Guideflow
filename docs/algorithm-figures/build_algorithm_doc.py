from pathlib import Path
import re
from docx import Document
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_SECTION_START, WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'docs/DLBCL-Evidence算法设计与实现.md'
OUTPUT=ROOT/'docs/DLBCL-Evidence算法设计与实现.docx'
doc=Document()
section=doc.sections[0]
section.page_width=Inches(8.5); section.page_height=Inches(11)
section.top_margin=Cm(2.1); section.bottom_margin=Cm(2.1)
section.left_margin=Cm(2.2); section.right_margin=Cm(2.2)
section.header_distance=Cm(.9); section.footer_distance=Cm(.9)

def font(style,name,size,bold=False):
    style.font.name=name; style.font.size=Pt(size); style.font.bold=bold
    style.font.color.rgb=RGBColor(0,0,0)
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'),name)
    style.element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:ascii'),'Times New Roman')

font(doc.styles['Normal'],'宋体',11)
normal=doc.styles['Normal'].paragraph_format
normal.line_spacing=1.3; normal.space_after=Pt(4)
normal.widow_control=True
for name,size in [('Title',20),('Subtitle',12),('Heading 1',15),('Heading 2',12),('Heading 3',11)]:
    font(doc.styles[name],'黑体',size,name!='Subtitle')
    p=doc.styles[name].paragraph_format
    p.space_before=Pt(12 if name=='Heading 1' else 8);p.space_after=Pt(6)
    p.keep_with_next=True
font(doc.styles['Caption'],'宋体',10)
doc.styles['Caption'].paragraph_format.space_after=Pt(7)
doc.styles['Caption'].paragraph_format.line_spacing=1.2
for st in doc.styles:
    ppr=st.element.find(qn('w:pPr'))
    if ppr is not None:
        for border in list(ppr.findall(qn('w:pBdr'))):ppr.remove(border)

def field(p,code):
    r=p.add_run(); f=OxmlElement('w:fldSimple'); f.set(qn('w:instr'),code); r._r.addnext(f)

header=section.header.paragraphs[0]
header.text='DLBCL-Evidence  系统算法设计与实现'
header.alignment=WD_ALIGN_PARAGRAPH.RIGHT
for r in header.runs:r.font.size=Pt(8);r.font.color.rgb=RGBColor(0,0,0)
footer=section.footer.paragraphs[0];footer.alignment=WD_ALIGN_PARAGRAPH.CENTER
footer.add_run('第 ');field(footer,'PAGE');footer.add_run(' 页')

def table(rows):
    t=doc.add_table(rows=1, cols=len(rows[0]));t.alignment=WD_TABLE_ALIGNMENT.CENTER
    t.autofit=False
    widths=([3.1,5.5,8.1] if len(rows[0])==3 else [8.0]*len(rows[0]))
    usable=17.1
    widths=[w*usable/sum(widths) for w in widths]
    for c,w in zip(t.columns,widths):c.width=Cm(w)
    for i,row in enumerate(rows):
        cells=t.rows[0].cells if i==0 else t.add_row().cells
        for j,(cell,value) in enumerate(zip(cells,row)):
            cell.width=Cm(widths[j]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            cell.text=value
            tcPr=cell._tc.get_or_add_tcPr()
            borders=OxmlElement('w:tcBorders')
            for edge in ('top','left','bottom','right','insideH','insideV'):
                e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
            tcPr.append(borders)
            margins=OxmlElement('w:tcMar')
            for edge in ('top','left','bottom','right'):
                e=OxmlElement('w:'+edge);e.set(qn('w:w'),'90');e.set(qn('w:type'),'dxa');margins.append(e)
            tcPr.append(margins)
            if i==0 or i%2==0:
                sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'E8EEF3' if i==0 else 'F6F7F8');tcPr.append(sh)
            for p in cell.paragraphs:
                p.paragraph_format.line_spacing=1.15;p.paragraph_format.space_after=Pt(1)
                p.paragraph_format.space_before=Pt(1)
                if i==0:p.paragraph_format.keep_with_next=True
                for r in p.runs:r.font.size=Pt(9.5);r.bold=(i==0)
        trPr=t.rows[i]._tr.get_or_add_trPr()
        cant=OxmlElement('w:cantSplit');trPr.append(cant)
        if i==0:
            repeat=OxmlElement('w:tblHeader');trPr.append(repeat)
    doc.add_paragraph().paragraph_format.space_after=Pt(1)

lines=SOURCE.read_text(encoding='utf-8').splitlines()
i=0
while i<len(lines):
    s=lines[i].strip()
    if not s:i+=1;continue
    if s.startswith('|'):
        rows=[]
        while i<len(lines) and lines[i].strip().startswith('|'):
            raw=lines[i].strip()
            if not re.match(r'^\|[\s:|\-]+\|$',raw):rows.append([x.strip() for x in raw.strip('|').split('|')])
            i+=1
        table(rows);continue
    if s.startswith('# '):
        p=doc.add_paragraph(s[2:],style='Title');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    elif s.startswith('## 面向'):
        p=doc.add_paragraph(s[3:],style='Subtitle');p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    elif s.startswith('版本日期'):
        p=doc.add_paragraph(s);p.alignment=WD_ALIGN_PARAGRAPH.CENTER
        for r in p.runs:r.font.size=Pt(10)
    elif s.startswith('## '):
        value=s[3:]
        if value=='1 引言':doc.add_page_break()
        p=doc.add_paragraph(value,style='Heading 1')
    elif s.startswith('### '):doc.add_paragraph(s[4:],style='Heading 2')
    else:
        p=doc.add_paragraph(s)
        if not re.match(r'^(关键词|\[\d|算法\d|\d+\.)',s):p.paragraph_format.first_line_indent=Pt(22)
        if re.match(r'^\d+\.',s):
            p.paragraph_format.left_indent=Cm(.4);p.paragraph_format.first_line_indent=Cm(-.4)
        if s.startswith('关键词'):
            for r in p.runs:r.bold=True
    i+=1

figures=[
('A','系统算法总览','01_system_overview.png','问题理解、主指南证据收集、生成及独立文献补充。页面摘要回流用于增强后续检索。'),
('B','自适应证据收集','02_evidence_acquisition.png','规划循环协调文字、候选页面和关系材料。示意关系不代表已核实的医学知识。'),
('C','证据约束生成与后处理','03_generation_and_delivery.png','生成后执行引用整理、配图定位与检查。路径选择以图片、来源能力和服务可用性为准。'),
('D','真实运行数据流转','04_worked_example.png','运行标识20261110-152841-b63521c1。数字为单次运行结果，不代表固定输出或性能指标。')]
for letter,title,filename,caption in figures:
    sec=doc.add_section(WD_SECTION_START.NEW_PAGE)
    sec.orientation=WD_ORIENT.LANDSCAPE;sec.page_width=Inches(11);sec.page_height=Inches(8.5)
    sec.left_margin=Cm(1.4);sec.right_margin=Cm(1.4);sec.top_margin=Cm(1.3);sec.bottom_margin=Cm(1.3)
    p=doc.add_paragraph('附图'+letter+' '+title,style='Heading 1')
    p.paragraph_format.space_before=Pt(0);p.paragraph_format.space_after=Pt(7)
    p=doc.add_paragraph();p.alignment=WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next=True
    p.add_run().add_picture(str(ROOT/'docs/algorithm-figures/imagegen-v2'/filename),width=Inches(9.8))
    p=doc.add_paragraph('附图'+letter+'  '+caption,style='Caption')
    p.paragraph_format.keep_with_next=False

doc.core_properties.title='DLBCL Evidence 系统算法设计与实现'
doc.core_properties.subject='面向淋巴瘤临床指南的自适应证据检索与多模态问答'
doc.core_properties.author='DLBCL-Evidence'
doc.core_properties.keywords='DLBCL; RAG; 多模态; 指南; 算法'
doc.save(OUTPUT)
print(OUTPUT)
