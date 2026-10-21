"""Real kernel checks, no model downloads. Run in each engine's isolated environment."""
import argparse
import json
import time
import traceback
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--output', required=True)
    args = parser.parse_args()
    report = {}
    import torch
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    report.update(torch=str(torch.__version__), cuda=torch.version.cuda,
                  gpu=torch.cuda.get_device_name(), capability=torch.cuda.get_device_capability())
    started = time.monotonic()
    torch.manual_seed(7)
    try:
        import spconv.pytorch as spconv
        coords = torch.cartesian_prod(torch.arange(4), torch.arange(4), torch.arange(4)).int()
        coords = torch.cat([torch.zeros((len(coords), 1), dtype=torch.int32), coords], dim=1).cuda()
        feats = torch.randn(len(coords), 4, device='cuda')
        sparse = spconv.SparseConvTensor(feats, coords, [4, 4, 4], 1)
        conv = spconv.SubMConv3d(4, 8, 3, padding=1, bias=False, algo=spconv.ConvAlgo.Native).cuda()
        output = conv(sparse).dense()
        # spconv 2 KRSC [out,z,y,x,in] -> Torch [out,in,z,y,x].
        dense = torch.nn.functional.conv3d(sparse.dense().double().cpu(), conv.weight.permute(0, 4, 1, 2, 3).double().cpu(), padding=1).float().cuda()
        torch.cuda.synchronize()
        error = (output - dense).abs().max().item()
        if not torch.allclose(output, dense, rtol=2e-4, atol=2e-4):
            raise RuntimeError(f'Sparse/dense convolution mismatch: {error}')
        report['sparse_conv'] = {'status': 'PASS', 'max_absolute_error': error, 'output_shape': list(output.shape)}
    except Exception:
        report['sparse_conv'] = {'status': 'FAILED', 'traceback': traceback.format_exc()}
    try:
        import flash_attn
        qkv = torch.randn(1, 64, 3, 4, 32, device='cuda', dtype=torch.float16)
        native = flash_attn.flash_attn_qkvpacked_func(qkv)
        q, k, v = [x.transpose(1, 2) for x in qkv.unbind(dim=2)]
        reference = torch.nn.functional.scaled_dot_product_attention(q, k, v).transpose(1, 2)
        torch.cuda.synchronize()
        error = (native - reference).abs().max().item()
        if not torch.allclose(native, reference, rtol=0.02, atol=0.01):
            raise RuntimeError(f'Attention mismatch {error}')
        report['flash_attention'] = {'status': 'PASS', 'max_absolute_error': error}
    except Exception:
        report['flash_attention'] = {'status': 'FAILED', 'traceback': traceback.format_exc()}
    report['duration_seconds'] = time.monotonic() - started
    path = Path(args.output); path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__': main()
