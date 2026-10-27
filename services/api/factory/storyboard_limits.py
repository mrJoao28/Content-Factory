"""Complexity budget for generated boards; imported/manual schema remains compatible."""

import math

from .schemas import Board


def constraints(context):
    duration = float(context.get("duration", 35))
    if not math.isfinite(duration) or not 0 < duration <= 600:
        raise ValueError("Storyboard target duration is invalid")
    return {
        "target_duration_seconds": duration,
        "max_scenes": min(60, max(1, math.ceil(duration / 5))),
        "max_layers_per_scene": 8,
        "max_keyframes_per_layer": 6,
        "instructions": "Use compact JSON and omit unchanged default fields. Use sparse keyframes, never one per video frame. Keyframe times are relative to each scene and must not exceed its duration. Scene durations must sum to the target within 0.01 second. Do not repeat character/asset descriptions in layers.",
    }


def generation_schema(response_type, context):
    schema = response_type.model_json_schema()
    if response_type is not Board:
        return schema, None
    limits = constraints(context)
    schema["properties"]["scenes"]["maxItems"] = limits["max_scenes"]
    schema["$defs"]["Scene"]["properties"]["layers"]["maxItems"] = limits["max_layers_per_scene"]
    schema["$defs"]["Scene"]["properties"]["narration"]["maxLength"] = 400
    schema["$defs"]["Layer"]["properties"]["keyframes"]["maxItems"] = limits["max_keyframes_per_layer"]
    return schema, limits


def validate_generated(result, context):
    if not isinstance(result, Board):
        return
    limits = constraints(context)
    if len(result.scenes) > limits["max_scenes"]:
        raise ValueError("Generated storyboard exceeds its scene budget")
    if abs(sum(scene.duration for scene in result.scenes) - limits["target_duration_seconds"]) > 0.01:
        raise ValueError("Generated storyboard durations must sum to the production target")
    for scene in result.scenes:
        if len(scene.layers) > limits["max_layers_per_scene"] or len(scene.narration) > 400:
            raise ValueError("Generated storyboard exceeds its layer or narration budget")
        for layer in scene.layers:
            if len(layer.keyframes) > limits["max_keyframes_per_layer"]:
                raise ValueError("Generated storyboard exceeds its keyframe budget")
            if any(frame.time > scene.duration for frame in layer.keyframes):
                raise ValueError("Generated keyframes exceed the scene duration")
