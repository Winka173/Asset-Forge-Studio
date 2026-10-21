"""Read-only existing environment capability probe; this is NOT an inference benchmark."""
import importlib.metadata
import json
import sys
from pathlib import Path

import torch

result = {'python': sys.version, 'torch': str(torch.__version__), 'cuda_runtime': torch.version.cuda,
          'device': torch.cuda.get_device_name(), 'capability': list(torch.cuda.get_device_capability()),
          'compiled_architectures': torch.cuda.get_arch_list(), 'inference': 'NOT_TESTED',
          'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions() if d.metadata['Name']}}
x = torch.ones((32, 32), device='cuda'); y = x @ x; torch.cuda.synchronize()
result['cuda_matmul_sum'] = y.sum().item()
result['cuda_smoke'] = 'PASS' if y.sum().item() == 32768 else 'FAIL'
Path(sys.argv[1]).write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps({k: v for k, v in result.items() if k != 'packages'}))
