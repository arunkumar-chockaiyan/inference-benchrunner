import pytest
import jinja2
from pathlib import Path
from unittest.mock import patch, AsyncMock
from services.sidecar import start_sidecar, render_sidecar_config

def test_template_rendering_all_variables(tmp_path):
    template_str = """
    file_storage: { directory: /tmp/otel-buffer/{{run_id}} }
    attributes: [{{run_id}}, {{model}}, {{engine}}, {{engine_host}}]
    metrics_target: {{metrics_host}}:{{metrics_port}}
    central_collector: {{central_collector_endpoint}}
    """
    
    rendered = render_sidecar_config(
        template_str=template_str,
        run_id="run123",
        model="llama3:8b",
        engine="ollama",
        engine_host="remote.ts.net",
        metrics_host="localhost",
        metrics_port=9091,
        central_collector_endpoint="http://collector:4317"
    )

    assert "run123" in rendered
    assert "llama3:8b" in rendered
    assert "ollama" in rendered
    assert "remote.ts.net" in rendered
    assert "localhost:9091" in rendered
    assert "http://collector:4317" in rendered

def test_template_strict_undefined():
    template_str = "Value is {{missing_var}}"
    with pytest.raises(jinja2.UndefinedError):
        render_sidecar_config(
            template_str=template_str,
            run_id="run123",
            model="llama",
            engine="vllm",
            engine_host="localhost",
            metrics_host="localhost",
            metrics_port=8000,
            central_collector_endpoint="host"
        )

@pytest.mark.asyncio
async def test_missing_otel_collector_endpoint_env(monkeypatch):
    monkeypatch.delenv("OTEL_COLLECTOR_ENDPOINT", raising=False)
    with pytest.raises(RuntimeError, match="OTEL_COLLECTOR_ENDPOINT is not set"):
        await start_sidecar("run1", "llama", "vllm", "host", "mhost", 8000)

@pytest.mark.asyncio
@patch("services.sidecar.asyncio.create_subprocess_exec")
async def test_sidecar_subprocess_args(mock_exec, monkeypatch, tmp_path):
    monkeypatch.setenv("OTEL_COLLECTOR_ENDPOINT", "http://otel:4317")
    mock_exec.return_value = AsyncMock()

    # Mock template file
    template_file = tmp_path / "sidecar.yaml.j2"
    template_file.write_text("ok: {{run_id}}")
    monkeypatch.setattr("services.sidecar.TEMPLATE_PATH", template_file)

    proc, config_path = await start_sidecar(
        "run123", "m", "e", "h", "mh", 8080
    )

    import asyncio
    mock_exec.assert_called_once_with(
        "otelcol-contrib",
        "--config",
        str(config_path),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL
    )
    assert config_path.name == "otel-sidecar-run123.yaml"
    assert config_path.exists()
