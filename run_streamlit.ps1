$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
.\.streamlit_venv\Scripts\streamlit.exe run streamlit_app.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
