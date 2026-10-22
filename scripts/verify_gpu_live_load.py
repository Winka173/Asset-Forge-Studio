"""Small real CUDA allocation to verify live telemetry; never a model output."""
import subprocess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from apps.api.jobs import exclusive_worker_lock

if __name__=='__main__':
    # Respect the same machine-wide slot as actual generation.
    with exclusive_worker_lock():
        python=Path.home()/'Tools/trellis2/code/venv/Scripts/python.exe'
        subprocess.run([str(python),'-u','-c',
            "import torch,time; assert torch.cuda.mem_get_info()[0]>2*1024**3; "
            "x=torch.ones(512*1024*1024,dtype=torch.uint8,device='cuda'); "
            "torch.cuda.synchronize(); print('REAL_CUDA_ALLOCATION_READY',flush=True); time.sleep(8)"],check=True)
