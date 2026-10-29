"""Customer ASR uses catalog labels and requires explicit audio-egress consent."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def test_material_library_exposes_explicit_cloud_asr_confirmation_without_secret_fields() -> None:
    script = (ROOT / "backlot" / "ui" / "workbench.js").read_text(encoding="utf-8")
    assert "/workbench/transcript-providers" in script
    functions = script[
        script.index("function transcriptProviderLabel("):
        script.index("async function startAssetMediaFineIndex(")
    ]
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is required to execute the frontend consent contract")
    harness = """
const vm = require('node:vm');
const calls = [], confirmations = [];
let accepted = false;
const context = {
  transcriptProviders: {default:'tencent', providers:{tencent:{
    label:'海客语音识别', detail:'本次按音轨时长计费。'
  }}},
  state:{}, render(){}, showToast(){},
  window:{confirm(message){confirmations.push(message); return accepted;}},
  api:async(path, request)=>{calls.push({path, request}); return {};}
};
vm.createContext(context);
vm.runInContext(FUNCTIONS, context, {timeout:1000});
(async()=>{
  await context.startAssetCloudTranscript({id:'test-asset'}, 'tencent');
  const rejectedCalls = calls.length;
  accepted = true;
  await context.startAssetCloudTranscript({id:'test-asset'}, 'tencent');
  console.log(JSON.stringify({rejectedCalls, confirmations, calls}));
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace("FUNCTIONS", json.dumps(functions))
    completed = subprocess.run(
        [node, "-e", harness], capture_output=True, text=True,
        encoding="utf-8", timeout=15, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["rejectedCalls"] == 0
    assert len(result["confirmations"]) == 2
    for message in result["confirmations"]:
        assert "海客语音识别" in message
        assert "按音轨时长计费" in message
        assert "只上传音轨" in message
        assert "提交结果不明时不会自动重复提交" in message
    assert result["calls"] == [{
        "path": "/assets/test-asset/media-index/jobs",
        "request": {"method": "POST", "body": {
            "stage": "coarse", "transcribe": True,
            "transcript_provider": "tencent", "remote_asr_confirmed": True,
        }},
    }]
    for secret_field in ("DOUBAO_ASR_API_KEY", "TENCENT_SECRET_KEY", "DASHSCOPE_API_KEY", "api_key", "secret_key"):
        assert secret_field not in functions
