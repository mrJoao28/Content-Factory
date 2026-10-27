"""Authored demo plans, not generated results. These require real Blender rendering."""
from .visual_schema import VisualBoard


def demo(name):
    if name == "engineering":
        return VisualBoard.model_validate({"duration": 3, "scenes": [{"duration": 3,
            "environment": "engineering_studio", "lighting": "studio", "characters": [],
            "props": [{"prop_id": "gear_pair", "position": [0, 0, 0]}],
            "camera": [{"time": 0, "position": [0, -5, 2], "target": [0, 0, 1.2]}],
            "particles": 0}]})
    character = "milo" if name == "milo" else "dino"
    duration = 35 if name == "milo" else 3 if name == "slice" else 8
    shot = {"duration": duration, "environment": "magic_forest", "lighting": "soft_day",
            "characters": [{"character_id": character, "asset_version": character+"-v1", "position": [-.5, 0, 0]}],
            "props": [{"prop_id": "magic_egg", "position": [.6, -.15, .32]}],
            "camera": [{"time": 0, "position": [2, -5, 2.5], "target": [0, 0, 1.1]}],
            "actions": [{"character_id": character, "kind": "walk", "start": 0, "end": 2, "target": [0, 0, 0]}]}
    if name == "dino":
        shot["actions"] += [
            {"character_id": "dino", "kind": "surprise", "start": 2, "end": 3.5},
            {"character_id": "dino", "kind": "walk", "start": 3.5, "end": 4.5, "target": [.25, 0, 0]},
            {"character_id": "dino", "kind": "tilt", "start": 4.5, "end": 5.8},
            {"character_id": "dino", "kind": "smile", "start": 5.8, "end": 6.5},
            {"character_id": "dino", "kind": "reach", "start": 6.5, "end": 8, "prop_id": "magic_egg"},
        ]
        shot["dialogues"] = [{"character_id": "dino", "start": 2, "text": "Wow! What's that?"}]
        shot["camera"] += [
            {"time": 5, "position": [1.6, -3.8, 1.4], "target": [.4, 0, .7]},
            {"time": 8, "position": [1, -3, 2], "target": [.2, 0, 1.6]},
        ]
    if name != "milo":
        return VisualBoard.model_validate({"duration": duration, "scenes": [shot]})
    texts = ["Milo found a tiny star resting in the garden.",
             "It glowed softly, but it could not reach the sky.",
             "Milo leaned closer. A little help could make a big difference.",
             "Very gently, Milo lifted the star in one small hand.",
             "Its warm light shimmered across the sleepy flowers.",
             "Up it floated, back toward its sparkling friends.",
             "Milo waved goodnight. Even small helpers can brighten the world."]
    scenes = []
    for i, text in enumerate(texts):
        action = ["look", "surprise", "reach", "hold", "hold", "release", "wave"][i]
        # Each cut establishes its own complete scene state; no hidden previous-shot state.
        actions = []
        if i == 5:
            actions.append({"character_id": "milo", "kind": "hold", "start": 0, "end": 2, "prop_id": "little_star"})
        entry = {"character_id": "milo", "kind": action, "start": 2 if i == 5 else 0,
                 "end": 5, "target": [.45, -.3, 1]}
        if action in ("reach", "hold", "release"):
            entry["prop_id"] = "little_star"
        if action == "release":
            entry["target"] = [.5, -.3, 3]
        actions.append(entry)
        scenes.append({"duration": 5, "environment": "dusk_garden", "lighting": "warm_dusk", "narration": text,
                       "characters": [{"character_id": "milo", "asset_version": "milo-v1", "position": [0, 0, 0]}],
                       "props": [{"prop_id": "little_star", "position": [.5, -.3, .35 if i < 3 else 3 if i == 6 else 1]}],
                       "actions": actions, "particles": 0,
                       "camera": [{"time": 0, "position": [1.6, -5, 2.4], "target": [.2, 0, 1.1]}]})
    return VisualBoard.model_validate({"duration": 35, "scenes": scenes})
