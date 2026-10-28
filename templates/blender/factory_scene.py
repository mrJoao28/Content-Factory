"""Repository-owned Blender 4.5/5.2 LTS script. Input is validated data, never Python.

Original procedural assets, generated deterministically; no imported files, drivers or add-ons.
Cycles devices are selected explicitly; GPU failure never falls back to CPU. Visual QA is still required.
"""
import json
import math
import os
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector

MATERIALS = {}
SPHERE = None


def material(name, color, emission=0):
    if name in MATERIALS:
        return MATERIALS[name]
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    # 5.x always uses shader nodes; use_nodes is deprecated and has no effect.
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    node = mat.node_tree.nodes.get("Principled BSDF")
    node.inputs["Base Color"].default_value = (*color, 1)
    node.inputs["Roughness"].default_value = 0.48
    node.inputs["Emission Color"].default_value = (*color, 1)
    node.inputs["Emission Strength"].default_value = emission
    MATERIALS[name] = mat
    return mat


def empty(name, location=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location = location
    return obj


def oval(name, location, scale, mat, parent=None):
    global SPHERE
    if SPHERE is None:
        bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12)
        SPHERE = bpy.context.object.data
        bpy.data.objects.remove(bpy.context.object, do_unlink=True)
        for polygon in SPHERE.polygons:
            polygon.use_smooth = True
    obj = bpy.data.objects.new(name, SPHERE)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.location, obj.scale = location, scale
    # Per-object material assignment preserves shared geometry.
    if not SPHERE.materials:
        SPHERE.materials.append(mat)
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = mat
    return obj


def stroke(name, points, mat, parent, radius=0.025):
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.bevel_depth, curve.bevel_resolution = radius, 2
    spline = curve.splines.new("POLY")
    spline.points.add(len(points)-1)
    for p, xyz in zip(spline.points, points):
        p.co = (*xyz, 1)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(mat)
    return obj


def character(identity):
    robot = identity == "milo"
    root = empty(identity)
    skin = material("milo_blue" if robot else "dino_green", (0.06, .35, .72) if robot else (.17, .58, .22))
    yellow = material("warm_yellow", (1, .68, .12))
    brown = material("brown_iris", (.23, .085, .025))
    dark = material("soft_dark", (.025, .035, .055))
    white = material("eye_white", (.98, .96, .88))
    metal = material("joint_blue", (.045, .12, .23))
    body = oval(identity+"_torso", (0, 0, .92), (.51, .36, .62), skin, root)
    head = empty("head_pivot", (0, -.05, 1.63), root)
    oval("rounded_head", (0, 0, 0), (.51, .37, .43), skin, head)
    if robot:
        # Rounded mesh volumes, articulated ball joints and a sculpted heart badge.
        oval("heart_left", (-.065, -.355, 1.03), (.105, .045, .115), yellow, root)
        oval("heart_right", (.065, -.355, 1.03), (.105, .045, .115), yellow, root)
        oval("heart_tip", (0, -.36, .94), (.10, .045, .115), yellow, root)
        oval("antenna", (0, 0, .45), (.045, .045, .12), metal, head)
        oval("antenna_tip", (0, 0, .58), (.08, .08, .08), yellow, head)
    else:
        oval("small_yellow_belly", (0, -.33, .84), (.29, .07, .35), yellow, root)
        oval("snout", (0, -.30, -.13), (.34, .21, .19), skin, head)
        for x in (-.10, .10):
            oval("nostril", (x, -.493, -.07), (.025, .018, .022), dark, head)
        tail = oval("stable_tail", (0, .51, .61), (.22, .65, .22), skin, root)
        tail.rotation_euler.x = -.15
        for i in range(3):
            oval("back_spot", (0, .31+i*.20, 1.0-i*.13), (.105, .09, .11), yellow, root)
    lids, pupils = [], []
    for x in (-.20, .20):
        eye = empty("eye_group", (x, -.30, .08), head)
        oval("eye", (0, 0, 0), (.165, .095, .19), white, eye)
        pupil = oval("brown_iris", (0, -.092, 0), (.09, .035, .115), brown, eye)
        oval("pupil", (0, -.122, 0), (.047, .018, .069), dark, eye)
        oval("catchlight", (-.025, -.14, .04), (.025, .012, .029), white, eye)
        lids.append(eye)
        pupils.append(pupil)
    mouth = stroke("smile", [(-.15, -.48, -.17), (-.075, -.50, -.21), (0, -.51, -.22),
                              (.075, -.50, -.21), (.15, -.48, -.17)], dark, head, .018)
    open_mouth = oval("mouth_open", (0, -.49, -.19), (.09, .025, .065), dark, head)
    hands, shoulders, feet = [], [], []
    for side in (-1, 1):
        shoulder = empty("shoulder", (side*.47, 0, 1.22), root)
        oval("shoulder_joint", (0, 0, 0), (.11, .11, .11), metal if robot else skin, shoulder)
        oval("arm", (side*.035, 0, -.19), (.105, .11, .22 if robot else .17), skin, shoulder)
        hand = empty("hand", (side*.04, 0, -.39 if robot else -.30), shoulder)
        oval("rounded_hand", (0, 0, 0), (.13, .12, .13), skin, hand)
        hip = empty("hip", (side*.26, 0, .48), root)
        oval("leg", (0, 0, -.12), (.16, .17, .26), skin, hip)
        oval("knee", (0, -.015, -.23), (.14, .145, .14), metal if robot else skin, hip)
        foot = oval("foot", (side*.26, -.12, .15), (.22, .29, .15), skin, root)
        feet.append(foot)
        hands.append(hand)
        shoulders.append(shoulder)
    return {"root": root, "body": body, "head": head, "hands": hands, "shoulders": shoulders,
            "feet": feet, "eyes": lids, "pupils": pupils, "mouth": mouth, "open_mouth": open_mouth}


def environment(kind):
    green = material("grass", (.14, .28, .14))
    ground = material("studio_floor", (.15, .19, .25)) if kind == "engineering_studio" else green
    oval("ground", (0, 0, -.23), (12, 12, .23), ground)
    if kind == "engineering_studio":
        return
    trunk = material("bark", (.29, .13, .065))
    leaf = material("foliage", (.07, .29, .13))
    pink = material("petal", (.88, .32, .52))
    cream = material("mushroom_stem", (.88, .78, .53))
    cap = material("mushroom_cap", (.72, .16, .13))
    rng = random.Random(741)
    for x, y in [(-3, 2), (2.8, 2.5), (-2.2, 4), (1.6, 4.8), (-3.7, -.1)]:
        oval("trunk", (x, y, 1.45), (.25, .28, 1.5), trunk)
        for dx in (-.3, .4):
            oval("canopy", (x+dx, y, 3), (1.05, .85, 1.2), leaf)
    for i in range(32):
        x, y = rng.uniform(-3, 3), rng.uniform(-1, 4)
        if abs(x) < 1.1 and y < 1:
            continue
        oval("grass_tuft", (x, y, .10), (.05, .07, .12), leaf)
        if i % 3 == 0:
            oval("stem", (x, y, .16), (.025, .025, .16), cream)
            for j in range(5):
                angle = j*math.tau/5
                oval("petal", (x+.07*math.cos(angle), y+.07*math.sin(angle), .33), (.075, .045, .035), pink)
            oval("pollen", (x, y, .35), (.04, .04, .025), cream)
        if i % 7 == 0:
            oval("mushroom_stem", (x+.2, y, .15), (.06, .06, .15), cream)
            oval("mushroom_cap", (x+.2, y, .30), (.19, .19, .09), cap)


def prop(identity):
    root = empty(identity)
    glow = material("egg_glow", (.12, .42, 1), .7)
    if identity == "magic_egg":
        oval("egg_volume", (0, 0, 0), (.23, .23, .32), glow, root)
    elif identity == "little_star":
        gold = material("star_gold", (1, .65, .12), .5)
        oval("star_core", (0, 0, 0), (.17, .09, .17), gold, root)
        for i in range(5):
            angle = math.tau*i/5
            arm = oval("star_point", (.20*math.sin(angle), 0, .20*math.cos(angle)), (.09, .09, .22), gold, root)
            arm.rotation_euler.y = angle
    else:
        steel = material("mechanism_blue", (.18, .48, .74))
        for side in (-1, 1):
            gear = empty("gear", (side*.65, 0, 1.2), root)
            oval("hub", (0, 0, 0), (.59, .15, .59), steel, gear)
            for i in range(16):
                angle = i*math.tau/16
                tooth = oval("tooth", (.61*math.sin(angle), 0, .61*math.cos(angle)), (.10, .14, .14), steel, gear)
                tooth.rotation_euler.y = angle
            oval("axle", (0, -.18, 0), (.12, .06, .12), material("axle", (.8, .77, .66)), gear)
    return root


def lerp(a, b, u):
    return Vector(a).lerp(Vector(b), u)


def smooth(u):
    u = max(0, min(1, u))
    return u*u*(3-2*u)


def pose(rig, actor, shot, t):
    root, head = rig["root"], rig["head"]
    root.location = actor["position"]
    root.rotation_euler.z = math.radians(actor["heading"])
    head.rotation_euler = (0, 0, 0)
    rig["mouth"].scale = (1, 1, 1)
    rig["body"].scale.z = .62*(1+.012*math.sin(t*2.3))
    for shoulder in rig["shoulders"]:
        shoulder.rotation_euler = (0, 0, 0)
    for side, foot in zip((-1, 1), rig["feet"]):
        foot.location = (side*.26, -.12, .15)
    rig["open_mouth"].hide_render = True
    for action in shot["actions"]:
        if action["character_id"] != actor["character_id"] or t < action["start"]:
            continue
        u = smooth((t-action["start"])/(action["end"]-action["start"]))
        active = t < action["end"]
        kind = action["kind"]
        if kind == "walk":
            origin = root.location.copy()
            root.location = lerp(origin, action["target"], u)
            if active:
                phase = (t-action["start"])*math.tau*1.4
                for side, foot, arm in zip((-1, 1), rig["feet"], rig["shoulders"]):
                    foot.location.y += .12*math.sin(phase)*side
                    foot.location.z += .08*max(0, math.sin(phase)*side)
                    arm.rotation_euler.x = .20*math.sin(phase)*side
        if active:
            blend = math.sin(math.pi*u)
            if kind == "surprise":
                head.rotation_euler.x = -.16*blend
                rig["open_mouth"].hide_render = False
            if kind == "tilt":
                head.rotation_euler.y = .24*blend
            if kind == "smile":
                rig["mouth"].scale.x = 1+.25*blend
            if kind == "wave":
                rig["shoulders"][1].rotation_euler.y = -1.9*blend
                rig["shoulders"][1].rotation_euler.x = .22*math.sin(t*9)*blend
            if kind in ("reach", "hold", "release"):
                rig["shoulders"][1].rotation_euler.x = -1.1*(u if kind == "reach" else 1-u if kind == "release" else 1)
            if kind == "look" and action.get("target"):
                delta = Vector(action["target"])-root.location
                head.rotation_euler.z = max(-.5, min(.5, math.atan2(delta.x, -delta.y))) * blend
                head.rotation_euler.x = max(-.25, min(.25, (1.5-delta.z)*.1))*blend
    blink = .05 if t % 3.7 < .10 else 1
    for eye in rig["eyes"]:
        eye.scale.z = blink
    for line in shot["dialogues"]:
        if line["character_id"] == actor["character_id"] and any(abs(t-m) < .06 for m in line["mouth_times"]):
            rig["open_mouth"].hide_render = False
    rig["mouth"].hide_render = not rig["open_mouth"].hide_render


def configure_device(scene, backend):
    if backend not in {"CPU", "OPTIX", "CUDA"}:
        raise ValueError("Unsupported explicit Cycles backend")
    devices = []
    if backend != "CPU":
        preferences = bpy.context.preferences.addons["cycles"].preferences
        preferences.compute_device_type = backend
        preferences.refresh_devices()
        for device in preferences.devices:
            device.use = device.type == backend
            if device.use:
                devices.append({"name": device.name, "type": device.type, "id": device.id})
        if not devices:
            raise RuntimeError("Requested Cycles GPU backend has no supported devices; explicitly choose CPU if desired")
    scene.cycles.device = "CPU" if backend == "CPU" else "GPU"
    return {"backend": backend, "devices": devices, "blender": bpy.app.version_string}


def setup(shot, cfg):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    device = configure_device(scene, cfg.get("backend", "CPU"))
    if cfg.get("device_report"):
        Path(cfg["device_report"]).write_text(json.dumps(device), encoding="utf-8")
    scene.cycles.seed = cfg.get("seed", 0)
    scene.cycles.samples = cfg.get("samples", 8 if cfg["quality"] == "preview" else 32)
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 3
    scene.render.threads_mode = "FIXED"
    scene.render.threads = cfg["threads"]
    # Reuse bounded scene data between animation frames instead of rebuilding Cycles
    # for every bpy.ops.render call. Does not retain the sequence's pixel buffers.
    scene.render.use_persistent_data = True
    scene.render.resolution_x, scene.render.resolution_y = cfg["width"], cfg["height"]
    scene.render.resolution_percentage = 100
    scene.render.fps = cfg["fps"]
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.view_settings.view_transform = "AgX"
    scene.world.color = (.18, .20, .26)
    if bpy.app.version < (5, 0, 0):
        scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (.18, .20, .26, 1)
    background.inputs["Strength"].default_value = .35
    environment(shot["environment"])
    actors = {a["character_id"]: character(a["character_id"]) for a in shot["characters"]}
    props = {}
    for entry in shot["props"]:
        props[entry["prop_id"]] = prop(entry["prop_id"])
        props[entry["prop_id"]].location = entry["position"]
    bpy.ops.object.camera_add()
    scene.camera = bpy.context.object
    scene.camera.data.dof.use_dof = True
    scene.camera.data.dof.aperture_fstop = 7
    for name, pos, power, size in [("key", (2, -4, 6), 650, 5), ("fill", (-4, -2, 3), 300, 5), ("rim", (0, 4, 5), 800, 4)]:
        bpy.ops.object.light_add(type="AREA", location=pos)
        light = bpy.context.object
        light.name = name
        light.data.energy, light.data.shape, light.data.size = power, "DISK", size
        light.rotation_euler = (Vector((0, 0, 1))-light.location).to_track_quat("-Z", "Y").to_euler()
        if shot["lighting"] == "warm_dusk":
            light.data.color = (1, .72, .52) if name == "key" else (.58, .69, 1)
    particles = []
    if "magic_egg" in props:
        for i in range(shot["particles"]):
            particles.append(oval("magic_sparkle", (0, 0, 0), (.018, .018, .018), material("sparkle", (.8, .65, 1), 1.5)))
    return scene, actors, props, particles


def update(scene, actors, props, particles, shot, t):
    for actor in shot["characters"]:
        pose(actors[actor["character_id"]], actor, shot, t)
    # Deterministic evaluation from the start allows frame-level resume.
    bpy.context.view_layer.update()
    for entry in shot["props"]:
        obj = props[entry["prop_id"]]
        obj.location = entry["position"]
        holding = None
        for action in shot["actions"]:
            if action.get("prop_id") != entry["prop_id"] or t < action["start"]:
                continue
            if action["kind"] == "hold":
                holding = action
            if action["kind"] == "release" and holding:
                # Evaluate the exact release pose, then restore the current pose.
                actor = next(a for a in shot["characters"] if a["character_id"] == action["character_id"])
                pose(actors[actor["character_id"]], actor, shot, action["start"])
                bpy.context.view_layer.update()
                release_position = actors[actor["character_id"]]["hands"][1].matrix_world.translation.copy()
                u = smooth((t-action["start"])/(action["end"]-action["start"]))
                obj.location = lerp(release_position, action["target"], u) if action.get("target") else release_position
                pose(actors[actor["character_id"]], actor, shot, t)
                holding = None
        bpy.context.view_layer.update()
        if holding:
            obj.location = actors[holding["character_id"]]["hands"][1].matrix_world.translation
        if entry["prop_id"] == "gear_pair":
            for index, gear in enumerate(obj.children):
                gear.rotation_euler.y = t*.7*(1 if index == 0 else -1)+(0 if index == 0 else math.pi/16)
    keys = shot["camera"]
    a = b = keys[0]
    for key in keys:
        if key["time"] <= t:
            a = b = key
        else:
            b = key
            break
    u = smooth((t-a["time"])/(b["time"]-a["time"])) if a is not b else 0
    cam = scene.camera
    cam.location = lerp(a["position"], b["position"], u)
    target = lerp(a["target"], b["target"], u)
    cam.rotation_euler = (target-cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.lens = a["lens"]+(b["lens"]-a["lens"])*u
    cam.data.dof.focus_distance = (target-cam.location).length
    if "magic_egg" in props:
        palette = [(.12, .42, 1), (1, .28, .52), (1, .72, .10), (.52, .18, 1)]
        phase = t/shot["duration"]*3
        index = min(2, int(phase))
        color = lerp(palette[index], palette[index+1], smooth(phase-index))
        node = MATERIALS["egg_glow"].node_tree.nodes.get("Principled BSDF")
        node.inputs["Base Color"].default_value = (*color, 1)
        node.inputs["Emission Color"].default_value = (*color, 1)
        for i, particle in enumerate(particles):
            angle = i*2.4+t*.4
            particle.location = props["magic_egg"].location+Vector((.4*math.cos(angle), .4*math.sin(angle), .1+.5*((i*.17+t*.2) % 1)))


def main():
    manifest_path = Path(sys.argv[sys.argv.index("--")+1]).resolve()
    cfg = json.loads(manifest_path.read_text(encoding="utf-8"))
    # Parent validates this manifest and chooses the output directory; no paths from AI.
    output = manifest_path.parent
    bpy.context.preferences.filepaths.use_scripts_auto_execute = False
    board = cfg["board"]
    scene_offset = 0
    for shot in board["scenes"]:
        count = round(shot["duration"]*cfg["fps"])
        required = [i for i in range(count)
                    if cfg.get("frame_start", 1) <= scene_offset+i+1 <= cfg.get("frame_end", 18000)
                    and not (output/f"{scene_offset+i+1:06}.png").is_file()]
        if not required:
            scene_offset += count
            continue
        scene, actors, props, particles = setup(shot, cfg)
        for index in required:
            frame = scene_offset+index+1
            scene.frame_set(frame)
            update(scene, actors, props, particles, shot, index/cfg["fps"])
            partial = output/f"{frame:06}.partial.png"
            scene.render.filepath = str(partial)
            bpy.ops.render.render(write_still=True)
            os.replace(partial, output/f"{frame:06}.png")
            print("FACTORY_FRAME "+str(frame), flush=True)
        scene_offset += count
    print("FACTORY_COMPLETE", flush=True)


if __name__ == "__main__":
    main()
