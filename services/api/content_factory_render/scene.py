"""Trusted 3D catalog. Metres, Z-up; characters face -Y at heading zero."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CATALOG_VERSION = "factory-3d-v1"
CHARACTERS = {"dino": "dino-v1", "milo": "milo-v1"}
ENVIRONMENTS = ("magic_forest", "dusk_garden", "engineering_studio")
ACTIONS = ("idle", "walk", "stop", "look", "surprise", "tilt", "smile", "reach", "hold", "release", "wave", "clap", "sway", "dance")
PROPS = ("magic_egg", "little_star", "gear_pair")
Number = Annotated[float, Field(ge=-20, le=20)]
Vector = tuple[Number, Number, Number]


class Data(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Actor(Data):
    character_id: Literal["dino", "milo"]
    asset_version: Literal["dino-v1", "milo-v1"]
    position: Vector = (0, 0, 0)
    heading: float = Field(default=0, ge=-180, le=180)

    @model_validator(mode="after")
    def identity(self):
        if CHARACTERS[self.character_id] != self.asset_version:
            raise ValueError("Character/rig version mismatch")
        if self.position[2] != 0:
            raise ValueError("Characters must start on the ground (Z=0)")
        return self


class Prop(Data):
    prop_id: Literal["magic_egg", "little_star", "gear_pair"]
    position: Vector = (0.8, 0.2, 0.3)


class Action(Data):
    character_id: Literal["dino", "milo"]
    kind: Literal["idle", "walk", "stop", "look", "surprise", "tilt", "smile", "reach", "hold", "release", "wave", "clap", "sway", "dance"]
    start: float = Field(ge=0, le=600)
    end: float = Field(gt=0, le=600)
    target: Vector | None = None
    prop_id: Literal["magic_egg", "little_star"] | None = None
    bpm: float = Field(default=100, ge=40, le=200)


class CameraKey(Data):
    time: float = Field(ge=0, le=600)
    position: Vector = (3, -7, 3)
    target: Vector = (0, 0, 1.1)
    lens: float = Field(default=45, ge=24, le=85)


class Dialogue(Data):
    character_id: Literal["dino", "milo"]
    start: float = Field(ge=0, le=600)
    text: str = Field(min_length=1, max_length=200)
    # Editable approximate mouth openings, NOT phoneme-aligned lip sync.
    mouth_times: list[float] = Field(default_factory=list, max_length=40)


class Shot(Data):
    duration: float = Field(ge=0.25, le=60)
    environment: Literal["magic_forest", "dusk_garden", "engineering_studio"]
    lighting: Literal["soft_day", "warm_dusk", "studio"] = "soft_day"
    narration: str = Field(default="", max_length=600)
    characters: list[Actor] = Field(default_factory=list, max_length=2)
    props: list[Prop] = Field(default_factory=list, max_length=3)
    actions: list[Action] = Field(default_factory=list, max_length=24)
    camera: list[CameraKey] = Field(min_length=1, max_length=6)
    dialogues: list[Dialogue] = Field(default_factory=list, max_length=3)
    particles: int = Field(default=12, ge=0, le=24)
    singing: list[Dialogue] = Field(default_factory=list, max_length=24)

    @model_validator(mode="after")
    def timeline(self):
        actors = {a.character_id: a for a in self.characters}
        props = {p.prop_id: p for p in self.props}
        if len(actors) != len(self.characters) or len(props) != len(self.props):
            raise ValueError("Duplicate actor or prop")
        if not actors and "gear_pair" not in props:
            raise ValueError("Shot requires a character or engineering mechanism")
        if self.camera[0].time != 0 or any(
            a.time >= b.time for a, b in zip(self.camera, self.camera[1:])
        ):
            raise ValueError("Camera keys must start at zero and increase")
        if any(k.time > self.duration for k in self.camera):
            raise ValueError("Camera key outside shot")
        for key in self.camera:
            if sum((a-b)**2 for a, b in zip(key.position, key.target)) < 0.25:
                raise ValueError("Camera is too close to its target")
        previous_end = {}
        if any(a.start > b.start for a, b in zip(self.actions, self.actions[1:])):
            raise ValueError("Actions must be ordered by start time")
        positions = {name: actor.position for name, actor in actors.items()}
        held = {}
        for action in self.actions:
            if action.character_id not in actors or not 0 <= action.start < action.end <= self.duration:
                raise ValueError("Action actor or timing invalid")
            if action.start < previous_end.get(action.character_id, 0):
                raise ValueError("Actions for each actor must be ordered and non-overlapping")
            previous_end[action.character_id] = action.end
            if action.prop_id and action.prop_id not in props:
                raise ValueError("Action references an unavailable prop")
            if action.kind in {"hold", "release"} and not action.prop_id:
                raise ValueError("Hold/release requires a prop")
            if action.kind == "release" and held.get(action.prop_id) != action.character_id:
                raise ValueError("Release must follow hold by the same actor")
            if action.kind == "hold":
                if action.prop_id in held:
                    raise ValueError("Prop already held")
                held[action.prop_id] = action.character_id
            if action.kind == "release":
                del held[action.prop_id]
            if action.kind == "walk":
                if not action.target or action.target[2] != 0:
                    raise ValueError("Walking needs a grounded target")
                distance = sum((x-y)**2 for x, y in zip(positions[action.character_id], action.target))**0.5
                if distance / (action.end-action.start) > 0.8:
                    raise ValueError("Walking exceeds 0.8 metres/second")
                positions[action.character_id] = action.target
        for dialogue in [*self.dialogues, *self.singing]:
            if dialogue.character_id not in actors or dialogue.start >= self.duration:
                raise ValueError("Dialogue actor or timing invalid")
            if any(t < dialogue.start or t >= self.duration for t in dialogue.mouth_times):
                raise ValueError("Mouth timing outside dialogue/shot")
        return self


class VisualBoard(Data):
    catalog_version: Literal["factory-3d-v1"] = CATALOG_VERSION
    duration: float = Field(gt=0, le=3600)
    scenes: list[Shot] = Field(min_length=1, max_length=720)

    @model_validator(mode="after")
    def total(self):
        if abs(sum(s.duration for s in self.scenes) - self.duration) > 0.000001:
            raise ValueError("3D scene durations must equal the project duration; regenerate planning")
        return self

    def validate_project(self, duration, fps):
        if abs(self.duration - duration) > 0.000001:
            raise ValueError("3D storyboard differs from configured project duration")
        for scene in self.scenes:
            if abs(scene.duration*fps - round(scene.duration*fps)) > 0.000001:
                raise ValueError("Scene duration must represent whole frames at the selected FPS")
        return self


class VisualSettings(Data):
    engine: Literal["compositor_2d", "blender_3d"] = "compositor_2d"
    execution_location: Literal["local", "colab"] = "local"
    external_hardware: Literal["GPU", "CPU", "OPTIX", "CUDA"] = "GPU"
    quality: Literal["preview", "final"] = "preview"
    character: Literal["dino", "milo"] = "dino"
    environment: Literal["magic_forest", "dusk_garden", "engineering_studio"] = "magic_forest"
    resolution: Literal["360x640", "720x1280", "1080x1920"] = "360x640"
    fps: Literal[24, 30] = 24
    catalog_version: Literal["factory-3d-v1"] = CATALOG_VERSION

    @model_validator(mode="after")
    def location(self):
        if self.execution_location == "colab" and self.engine != "blender_3d":
            raise ValueError("Colab execution requires Blender 3D")
        return self


def catalog():
    return {"version": CATALOG_VERSION, "characters": CHARACTERS, "environments": ENVIRONMENTS,
            "actions": ACTIONS, "props": PROPS, "units": "metres, Z-up, heading degrees; characters face -Y at zero heading",
            "timing": "scene-relative seconds; frame 1 is t=0; N frames cover [0, duration)"}
