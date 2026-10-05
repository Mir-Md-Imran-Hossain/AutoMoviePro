# Render Runtime Integration — BUILD-04D

## Modules

| File | Role |
|------|------|
| `render_manifest.py` | Manifest builder |
| `render_request.py` | RenderRequestSpec + fingerprint |
| `render_validation.py` | Output validation |
| `render_provenance.py` | Provenance persistence |
| `mock_render_provider.py` | Offline mock |
| `render_runtime.py` | execute_render_request |
| `render_bridge.py` | idempotent_compose_final_video |

## Modified

- `video_pipeline.py` — compose phase uses render bridge

## Atomic output

`final_{type}.tmp.mp4` → validate → `os.replace` → `final_{type}.mp4`
