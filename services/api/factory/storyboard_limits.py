"""Complexity budget for generated boards; imported/manual schema remains compatible."""

import math

from .schemas import Board


def constraints(context):
    duration = float(context.get("duration", 35))
    if not math.isfinite(duration) or not 0 < duration <= 3600:
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
    from .visual_schema import VisualBoard
    if response_type is VisualBoard:
        return schema, {"target_duration_seconds": context["duration"], "max_scenes": min(720, max(1, math.ceil(context['duration']/5))),
                        "instructions": "Compact JSON. Scene durations must sum exactly to duration. Use only the supplied catalog and selected character/environment. At most 2 actors, 3 props, 24 actions and 6 camera keys per scene. Ground Z=0. No overlapping actions per actor. No code. Narration must fit the scene. Camera uses metres Z-up; characters face -Y at heading 0. Reuse asset versions."}
    if response_type is not Board:
        return schema, None
    limits = constraints(context)
    schema["properties"]["scenes"]["maxItems"] = limits["max_scenes"]
    schema["$defs"]["Scene"]["properties"]["layers"]["maxItems"] = limits["max_layers_per_scene"]
    schema["$defs"]["Scene"]["properties"]["narration"]["maxLength"] = 400
    schema["$defs"]["Layer"]["properties"]["keyframes"]["maxItems"] = limits["max_keyframes_per_layer"]
    return schema, limits


def validate_generated(result, context):
    from .visual_schema import VisualBoard
    if isinstance(result, VisualBoard):
        result.validate_project(context["duration"], context.get("fps", 24))
        selection = context.get("visual_selection", {})
        musical = context.get('music_plan', {})
        cast = musical.get('characters') or [selection.get('character')]
        environment = musical.get('environment') or selection.get('environment')
        for scene in result.scenes:
            if context.get("channel") == "wondernest" and not set(cast).intersection(
                actor.character_id for actor in scene.characters):
                raise ValueError("Children's 3D scenes must contain the selected character")
            if environment and scene.environment != environment:
                raise ValueError("Use the selected environment")
            if any(actor.character_id not in cast for actor in scene.characters):
                raise ValueError("Use the selected character")
        return
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
