"""One Responses reference-image edit, with no automatic resubmission."""

import base64

from . import adapters


def execute(config, inputs, file_dir, upstream_id=None):
    # A synchronous Responses ID is not an asynchronous job polling token.
    # An interrupted/unknown call requires reconciliation, never a second POST.
    if upstream_id:
        raise adapters.Uncertain()
    image = (file_dir / inputs["image_file"]).read_bytes()
    mime = "image/png" if image.startswith(b"\x89PNG") else "image/jpeg"
    image_model = config.get("refinement_image_model", "gpt-image-2")
    result = adapters.http(
        config["base_url"].rstrip("/") + "/responses",
        {"Authorization": "Bearer " + config["api_key"], "Content-Type": "application/json"},
        {"model": config.get("refinement_text_model", "gpt-5.6"),
         "stream": False, "store": False,
         "tools": [{"type": "image_generation", "model": image_model, "size": "1024x1280"}],
         "tool_choice": {"type": "image_generation"},
         "input": [{"role": "user", "content": [
             {"type": "input_text", "text": "Edit the attached image. Call image_generation once and return the image.\n\n" + inputs["prompt"]},
             {"type": "input_image", "image_url": "data:" + mime + ";base64," + base64.b64encode(image).decode("ascii")},
         ]}]}, timeout=240,
    )
    if not isinstance(result, dict) or not isinstance(result.get("output"), list):
        raise adapters.Uncertain()
    calls = [item for item in result["output"] if isinstance(item, dict) and item.get("type") == "image_generation_call"]
    # Per-edit pricing covers exactly one completed image tool call. Multiple
    # tool calls or incomplete Responses need operator review, not settlement.
    if result.get("status") != "completed" or len(calls) != 1:
        raise adapters.Uncertain()
    call = calls[0]
    encoded = call.get("result")
    if call.get("status") != "completed" or not isinstance(encoded, str) or len(encoded) > 14 * 1024 * 1024:
        raise adapters.Uncertain()
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise adapters.Uncertain() from None
    if not raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"RIFF")):
        raise adapters.Uncertain()
    return {"usage": {"tasks": 1}, "upstream_id": str(result.get("id", "")),
            "result": {"image_base64": encoded, "source": image_model,
                       "response_id": str(result.get("id", "")), "tool_calls": 1,
                       "provider_usage": {k: v for k, v in (result.get("usage") or {}).items()
                                          if k in {"input_tokens", "output_tokens", "total_tokens"} and type(v) is int and v >= 0}}}
