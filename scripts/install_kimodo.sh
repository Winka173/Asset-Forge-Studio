#!/usr/bin/env bash
# Kimodo text-to-motion (NVIDIA, Apache-2.0 code; Kimodo-SOMA-RP weights under the NVIDIA Open Model license).
# Opt-in heavyweight install (~18 GB weights + ~5 GB env). No GPU work runs here.
# The LLM2Vec text encoder's base model is Meta-Llama-3-8B-Instruct; the gated meta-llama repo is replaced by the
# ungated NousResearch copy, whose safetensors have the same SHA-256 (checked against the Hub's LFS metadata).
set -euo pipefail
ROOT="$(cygpath -m "$(cd "$(dirname "$0")/.." && pwd)")"
TOOLS="$(cygpath -m "$HOME/Tools/kimodo")"; ENV="$ROOT/.local/envs/kimodo"; MODELS="$TOOLS/models"
[ -d "$TOOLS/code" ] || git clone --depth 1 https://github.com/nv-tlabs/kimodo "$TOOLS/code"
[ -x "$ENV/Scripts/python.exe" ] || py -3.11 -m venv "$ENV"
PY="$ENV/Scripts/python.exe"
"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
# The motion_correction C++ extension (foot-contact cleanup) builds with CMake + the installed Visual Studio C++ tools.
"$PY" -m pip install -q cmake
export PATH="$(cygpath -u "$ENV")/Lib/site-packages/cmake/data/bin:$PATH"  # the real binary; the pip shim fails inside build isolation
"$PY" -m pip install -q -e "$TOOLS/code[soma]" "huggingface_hub[hf_xet]"
mkdir -p "$MODELS"
dl() { "$PY" -c "import sys;from huggingface_hub import snapshot_download as s;print(s(sys.argv[1],local_dir=sys.argv[2],allow_patterns=sys.argv[3:] or None))" "$@"; }
dl nvidia/Kimodo-SOMA-RP-v1.2 "$MODELS/Kimodo-SOMA-RP-v1.2"
dl McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp "$MODELS/llm2vec-mntp"
dl McGill-NLP/LLM2Vec-Meta-Llama-3-8B-Instruct-mntp-supervised "$MODELS/llm2vec-supervised"
dl NousResearch/Meta-Llama-3-8B-Instruct "$MODELS/Meta-Llama-3-8B-Instruct" '*.json' '*.safetensors' 'LICENSE' 'USE_POLICY.md'
# Point both adapters at the local base model.
"$PY" - "$MODELS" <<'EOF'
import json, sys
from pathlib import Path
models = Path(sys.argv[1]); base = str(models / 'Meta-Llama-3-8B-Instruct')
for name in ('llm2vec-mntp', 'llm2vec-supervised'):
    path = models / name / 'adapter_config.json'; config = json.loads(path.read_text())
    config['base_model_name_or_path'] = base; path.write_text(json.dumps(config, indent=2))
print('adapters point at', base)
EOF
echo KIMODO_INSTALL_OK
