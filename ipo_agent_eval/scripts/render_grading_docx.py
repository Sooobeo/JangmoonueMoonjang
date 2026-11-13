"""Use the packaged render_docx rasterizer with Word on this Windows runtime.

The installed managed runtime has no bundled LibreOffice. Only its PDF export
function is replaced; the managed package and the original DOCX remain intact.
"""
import importlib.util
import os
import subprocess
from pathlib import Path

RUNTIME=Path(r"C:\Program Files\WindowsApps\OpenAI.CodexPrimaryRuntime.v26-1110-778-0_26.1110.778.0_x64__3k8sg7r9htsxt")
SKILL=Path(r"C:\Users\Insun\.codex\plugins\cache\openai-primary-runtime\documents\26.1110.11258\skills\documents")
os.environ['PATH']=str(RUNTIME/'dependencies/native/poppler/Library/bin')+os.pathsep+os.environ.get('PATH','')
spec=importlib.util.spec_from_file_location('packaged_render_docx',SKILL/'render_docx.py')
renderer=importlib.util.module_from_spec(spec); spec.loader.exec_module(renderer)

def word_pdf(doc_path,user_profile,convert_tmp_dir,stem,verbose=False):
    target=str(Path(convert_tmp_dir)/(stem+'.pdf'))
    command=[str(RUNTIME/'dependencies/native/powershell/pwsh.exe'),'-NoProfile','-File',str(Path(__file__).with_name('word_export_pdf.ps1')),'-InputPath',str(Path(doc_path).resolve()),'-OutputPath',target]
    result=subprocess.run(command,capture_output=True,text=True,timeout=180)
    log=result.stdout+'\n'+result.stderr
    if result.returncode or not Path(target).is_file(): raise RuntimeError('Word PDF export failed: '+log)
    return target,log

renderer.convert_to_pdf=word_pdf
if __name__=='__main__': renderer.main()
