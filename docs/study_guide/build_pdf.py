# docs/study_guide/build_pdf.py
# -*- coding: utf-8 -*-
import os
import subprocess
import sys

# Ensure current directory is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from sections_1_to_3 import get_section_1, get_section_2, get_section_3
from sections_4_to_6 import get_section_4, get_section_5, get_section_6
from sections_7_to_8 import get_section_7, get_section_8

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Route.it - 360-Degree Comprehensive Project Study Guide (SIH 2026)</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.css">
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/katex.min.js"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.8/dist/contrib/auto-render.min.js"
    onload="renderMathInElement(document.body);"></script>
  <style>
    @page {{
      size: A4;
      margin: 15mm 15mm 15mm 15mm;
      @bottom-right {{
        content: counter(page);
      }}
    }}
    
    * {{
      box-sizing: border-box;
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
    }}
    
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      color: #1e293b;
      background-color: #ffffff;
      line-height: 1.6;
      font-size: 13px;
      margin: 0;
      padding: 0;
    }}
    
    /* Document Header Cover */
    .doc-header {{
      background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 60%, #312e81 100%);
      color: #ffffff;
      padding: 40px 30px;
      border-radius: 12px;
      margin-bottom: 30px;
      border: 1px solid #4338ca;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2);
    }}
    
    .doc-badge {{
      display: inline-block;
      background: #4f46e5;
      color: #ffffff;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1px;
      text-transform: uppercase;
      padding: 4px 12px;
      border-radius: 9999px;
      margin-bottom: 15px;
    }}
    
    .doc-title {{
      font-size: 32px;
      font-weight: 900;
      letter-spacing: -0.5px;
      margin: 0 0 10px 0;
      color: #f8fafc;
    }}
    
    .doc-subtitle {{
      font-size: 16px;
      color: #cbd5e1;
      margin: 0 0 20px 0;
      font-weight: 400;
      max-width: 800px;
    }}
    
    .doc-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 20px;
      padding-top: 15px;
      border-top: 1px solid rgba(255, 255, 255, 0.15);
      font-size: 12px;
      color: #94a3b8;
    }}
    
    .doc-meta span strong {{
      color: #e2e8f0;
    }}
    
    /* Section Structure */
    .guide-section {{
      margin-bottom: 40px;
      page-break-after: always;
    }}
    
    .guide-section:last-child {{
      page-break-after: auto;
    }}
    
    .section-badge {{
      font-size: 11px;
      font-weight: 800;
      letter-spacing: 1.5px;
      color: #4f46e5;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    
    .section-title {{
      font-size: 24px;
      font-weight: 800;
      color: #0f172a;
      border-bottom: 2px solid #e2e8f0;
      padding-bottom: 8px;
      margin: 0 0 6px 0;
    }}
    
    .section-subtitle {{
      font-size: 13px;
      color: #64748b;
      margin: 0 0 20px 0;
      font-style: italic;
    }}
    
    /* Cards */
    .card {{
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 20px;
      box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
      page-break-inside: avoid;
    }}
    
    .card h2 {{
      font-size: 17px;
      color: #1e1b4b;
      margin-top: 0;
      margin-bottom: 12px;
      border-left: 4px solid #4f46e5;
      padding-left: 10px;
    }}
    
    .card h3 {{
      font-size: 14px;
      color: #334155;
      margin-top: 16px;
      margin-bottom: 8px;
    }}
    
    /* Custom Callout Boxes */
    .hinglish-box {{
      background: #fdf4ff;
      border-left: 4px solid #d946ef;
      border-top: 1px solid #fae8ff;
      border-right: 1px solid #fae8ff;
      border-bottom: 1px solid #fae8ff;
      border-radius: 6px;
      padding: 14px 18px;
      margin: 15px 0;
      page-break-inside: avoid;
    }}
    
    .hinglish-box h4 {{
      color: #a21caf;
      margin: 0 0 6px 0;
      font-size: 13px;
      font-weight: 700;
    }}
    
    .hinglish-box p {{
      margin: 0;
      color: #701a75;
      font-size: 12.5px;
      line-height: 1.5;
    }}
    
    .reality-check-box {{
      background: #fffbeb;
      border-left: 4px solid #f59e0b;
      border-top: 1px solid #fef3c7;
      border-right: 1px solid #fef3c7;
      border-bottom: 1px solid #fef3c7;
      border-radius: 6px;
      padding: 14px 18px;
      margin: 15px 0;
      page-break-inside: avoid;
    }}
    
    .reality-check-box h4 {{
      color: #b45309;
      margin: 0 0 6px 0;
      font-size: 13px;
      font-weight: 700;
    }}
    
    .reality-check-box p {{
      margin: 0;
      color: #92400e;
      font-size: 12.5px;
      line-height: 1.5;
    }}
    
    .emergency-plan-box {{
      background: #fef2f2;
      border: 1px solid #fecaca;
      border-left: 4px solid #ef4444;
      border-radius: 6px;
      padding: 16px;
      margin: 15px 0;
    }}
    
    .emergency-plan-box h3 {{
      color: #991b1b;
      margin-top: 0;
    }}
    
    .pitch-box {{
      background: #f0fdf4;
      border-left: 4px solid #22c55e;
      border-radius: 6px;
      padding: 16px;
      font-size: 13px;
      color: #166534;
      line-height: 1.6;
    }}
    
    /* Tables */
    .table-responsive {{
      overflow-x: auto;
      margin: 15px 0;
    }}
    
    .styled-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 11.5px;
      text-align: left;
    }}
    
    .styled-table thead tr {{
      background-color: #1e1b4b;
      color: #ffffff;
      text-align: left;
    }}
    
    .styled-table th, .styled-table td {{
      padding: 8px 10px;
      border: 1px solid #e2e8f0;
      vertical-align: top;
    }}
    
    .styled-table tbody tr:nth-of-type(even) {{
      background-color: #f8fafc;
    }}
    
    .styled-table tbody tr:hover {{
      background-color: #f1f5f9;
    }}
    
    .winner-row {{
      background-color: #ecfdf5 !important;
      font-weight: 600;
    }}
    
    .table-note {{
      font-size: 11px;
      color: #64748b;
      margin-top: 4px;
    }}
    
    /* Badges */
    .badge-real {{
      display: inline-block;
      background: #dcfce7;
      color: #15803d;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 700;
    }}
    
    .badge-sim {{
      display: inline-block;
      background: #fef3c7;
      color: #b45309;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 700;
    }}
    
    .badge-unfeasible {{
      display: inline-block;
      background: #fee2e2;
      color: #b91c1c;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10.5px;
      font-weight: 700;
    }}
    
    .badge-timeout {{
      display: inline-block;
      background: #fee2e2;
      color: #b91c1c;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
    }}
    
    .proof-tag {{
      display: inline-block;
      background: #f1f5f9;
      color: #475569;
      font-family: monospace;
      font-size: 10.5px;
      padding: 1px 6px;
      border-radius: 4px;
      border: 1px solid #cbd5e1;
      margin-top: 4px;
    }}
    
    /* Screenshots & Figures */
    .screenshot-container {{
      text-align: center;
      margin: 16px 0;
      page-break-inside: avoid;
    }}
    
    .guide-screenshot {{
      max-width: 100%;
      height: auto;
      max-height: 480px;
      border-radius: 6px;
      border: 1px solid #cbd5e1;
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
      display: inline-block;
    }}
    
    .screenshot-caption {{
      font-size: 11px;
      color: #64748b;
      margin-top: 6px;
      font-style: italic;
    }}
    
    /* Code & ASCII blocks */
    pre {{
      background: #0f172a;
      color: #e2e8f0;
      padding: 12px;
      border-radius: 6px;
      font-size: 11px;
      overflow-x: auto;
      line-height: 1.4;
      page-break-inside: avoid;
    }}
    
    code {{
      font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
      background: #f1f5f9;
      color: #475569;
      padding: 2px 4px;
      border-radius: 3px;
      font-size: 11.5px;
    }}
    
    pre code {{
      background: transparent;
      color: inherit;
      padding: 0;
    }}
    
    .ascii-diagram pre {{
      font-size: 9.5px;
      line-height: 1.25;
      background: #0f172a;
      color: #38bdf8;
      border: 1px solid #1e293b;
    }}
    
    /* Flow Steps */
    .flow-step {{
      display: flex;
      gap: 15px;
      margin-bottom: 12px;
      align-items: flex-start;
      page-break-inside: avoid;
    }}
    
    .step-num {{
      background: #4f46e5;
      color: #ffffff;
      font-size: 10px;
      font-weight: 800;
      padding: 4px 8px;
      border-radius: 4px;
      white-space: nowrap;
    }}
    
    .step-content {{
      flex: 1;
    }}
    
    .step-content h4 {{
      margin: 0 0 4px 0;
      font-size: 13px;
      color: #1e1b4b;
    }}
    
    .step-content p {{
      margin: 0;
      font-size: 12px;
      color: #475569;
    }}
    
    /* FAQ / Counter-Question Items */
    .faq-item {{
      margin-bottom: 14px;
      padding-bottom: 12px;
      border-bottom: 1px dashed #e2e8f0;
      page-break-inside: avoid;
    }}
    
    .faq-item:last-child {{
      border-bottom: none;
      margin-bottom: 0;
      padding-bottom: 0;
    }}
    
    .faq-q {{
      color: #0f172a;
      font-size: 12.5px;
      margin: 0 0 4px 0;
    }}
    
    .faq-a {{
      color: #334155;
      font-size: 12px;
      margin: 0;
      line-height: 1.5;
    }}
    
    /* Glossary Grid */
    .glossary-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }}
    
    .glossary-item {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 4px;
      padding: 8px 10px;
      font-size: 11px;
      page-break-inside: avoid;
    }}
    
    /* Quiz & Speaker Scripts */
    .quiz-q {{
      margin-bottom: 12px;
      padding: 8px 12px;
      background: #f8fafc;
      border-radius: 6px;
      border: 1px solid #e2e8f0;
      page-break-inside: avoid;
      font-size: 11.5px;
    }}
    
    .answer-key-box {{
      background: #f0fdf4;
      border: 1px solid #bbf7d0;
      border-radius: 6px;
      padding: 14px;
      margin-top: 20px;
      font-size: 11.5px;
      line-height: 1.6;
    }}
    
    .speaker-role {{
      background: #f8fafc;
      border-left: 4px solid #6366f1;
      padding: 12px 16px;
      margin-bottom: 12px;
      border-radius: 4px;
      page-break-inside: avoid;
    }}
    
    .speaker-role h4 {{
      margin: 0 0 6px 0;
      color: #312e81;
      font-size: 13px;
    }}
    
    .speaker-role p {{
      margin: 0;
      font-size: 12px;
      line-height: 1.5;
    }}
    
    .roadmap-phase {{
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 14px;
      margin-bottom: 12px;
      page-break-inside: avoid;
    }}
    
    .phase-badge {{
      font-size: 11.5px;
      font-weight: 800;
      color: #4f46e5;
      margin-bottom: 6px;
    }}
    
    .roadmap-phase ul {{
      margin: 0;
      padding-left: 18px;
      font-size: 12px;
    }}
    
    .math-block {{
      background: #f8fafc;
      padding: 8px 12px;
      border-radius: 6px;
      border: 1px solid #e2e8f0;
      margin: 10px 0;
      text-align: center;
      overflow-x: auto;
    }}
  </style>
</head>
<body>

  <!-- Cover Header -->
  <div class="doc-header">
    <div class="doc-badge">SMART INDIA HACKATHON 2026 &bull; PROBLEM STATEMENT SIH26137</div>
    <h1 class="doc-title">Route.it: 360-Degree Project Study Guide</h1>
    <p class="doc-subtitle">A Complete Technical, Algorithmic &amp; Operational Defense Guide for Student Team Presenters &bull; Quantum-Inspired Intelligent Delivery Orchestration System</p>
    <div class="doc-meta">
      <span><strong>Live Production:</strong> https://routeit.onrender.com</span>
      <span><strong>Git Commit:</strong> 457ed59 (main)</span>
      <span><strong>City Scenario:</strong> Vadodara, Gujarat (30 stops)</span>
      <span><strong>Routing Engine:</strong> Valhalla OpenStreetMap GIS</span>
      <span><strong>Numerical Core:</strong> Numba JIT (LLVM)</span>
      <span><strong>Date:</strong> November 2026</span>
    </div>
  </div>

  <!-- Table of Contents Card -->
  <div class="card" style="margin-bottom: 30px;">
    <h2>Document Table of Contents</h2>
    <div class="table-responsive">
      <table class="styled-table" style="font-size: 12px;">
        <tbody>
          <tr>
            <td><strong>Section 1</strong></td>
            <td><strong>Project in One Page:</strong> Core Problem, Stakeholders, Solution USPs, and 30-Second Elevator Pitch</td>
          </tr>
          <tr>
            <td><strong>Section 2</strong></td>
            <td><strong>Full Architecture &amp; Technology Decisions:</strong> Tech Stack Trade-offs, System &amp; Data-Flow Diagrams, and File Map</td>
          </tr>
          <tr>
            <td><strong>Section 3</strong></td>
            <td><strong>Button-by-Button System Guide:</strong> Complete Walkthrough of all 5 Portals, 9 Operational Sub-tabs, and Controls</td>
          </tr>
          <tr>
            <td><strong>Section 4</strong></td>
            <td><strong>The Algorithms Explained:</strong> CVRPTW Formulations, QPSO Wave Packet Physics, Prins Split DAG, and Authentic Benchmarks</td>
          </tr>
          <tr>
            <td><strong>Section 5</strong></td>
            <td><strong>Database, API, Security &amp; Deployment:</strong> SQLite 9-Table Schema, 30+ REST Endpoints, WebSockets, HMAC OTPs, and Render Cloud</td>
          </tr>
          <tr>
            <td><strong>Section 6</strong></td>
            <td><strong>Honest Limitations &amp; Future Scope:</strong> The 10 Reality Checks Every Teammate Must Know and 3-Phase Roadmap</td>
          </tr>
          <tr>
            <td><strong>Section 7</strong></td>
            <td><strong>The 70-Question Counter-Question Bank:</strong> Tough Technical &amp; Business Counter-Questions with Code Proof Tags</td>
          </tr>
          <tr>
            <td><strong>Section 8</strong></td>
            <td><strong>The Complete Presentation Kit:</strong> 12-Slide Deck, 5-Min &amp; 10-Min Scripts, Live Demo Stopwatch, 1-Page Cheat Sheet, Glossary, and 30-Question Quiz</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Section 1 -->
  {section_1}

  <!-- Section 2 -->
  {section_2}

  <!-- Section 3 -->
  {section_3}

  <!-- Section 4 -->
  {section_4}

  <!-- Section 5 -->
  {section_5}

  <!-- Section 6 -->
  {section_6}

  <!-- Section 7 -->
  {section_7}

  <!-- Section 8 -->
  {section_8}

</body>
</html>
"""

def main():
    print("Assembling HTML study guide content...")
    s1 = get_section_1()
    s2 = get_section_2()
    s3 = get_section_3()
    s4 = get_section_4()
    s5 = get_section_5()
    s6 = get_section_6()
    s7 = get_section_7()
    s8 = get_section_8()

    full_html = HTML_TEMPLATE.format(
        section_1=s1,
        section_2=s2,
        section_3=s3,
        section_4=s4,
        section_5=s5,
        section_6=s6,
        section_7=s7,
        section_8=s8
    )

    html_path = os.path.join(current_dir, "study_guide.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"HTML study guide generated: {html_path} ({len(full_html)} bytes)")

    # Compile to PDF using Microsoft Edge Headless
    pdf_path = os.path.join(current_dir, "Route_it_360_Study_Guide.pdf")
    edge_paths = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    ]
    
    edge_exe = None
    for ep in edge_paths:
        if os.path.exists(ep):
            edge_exe = ep
            break
            
    if not edge_exe:
        print("Microsoft Edge executable not found. Unable to compile PDF.")
        return

    print(f"Compiling PDF via Microsoft Edge Headless: {edge_exe} ...")
    cmd = [
        edge_exe,
        "--headless",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={pdf_path}",
        html_path
    ]
    
    res = subprocess.run(cmd, capture_output=True, text=True)
    if os.path.exists(pdf_path):
        size = os.path.getsize(pdf_path)
        print(f"SUCCESS: PDF created at {pdf_path} ({size} bytes)")
    else:
        print("PDF compilation failed:")
        print(res.stderr)

if __name__ == "__main__":
    main()
