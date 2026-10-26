import time

from sqlalchemy import delete, select

from .audio import Piper, mix_tracks
from .config import settings
from .db import Session
from .models import (
    Character,
    ProductionJob,
    RenderArtifact,
    SceneAsset,
    ScriptVersion,
    Series,
    Storyboard,
    VideoProject,
    VideoScene,
)
from .providers import get_provider, job_selection, validate_selection
from .queue import checkpoint, event
from .render import probe, render, validate_video
from .schemas import AgentResult, AudioMix, Board, Metadata, Script
from .security import ConfigurationRequired, digest, safe_path


def produce(job_id, owner, cancel=lambda: False):
    with Session() as db:
        job = db.get(ProductionJob, job_id)
        project = db.get(VideoProject, job.project_id)
        project_id, revision = project.id, project.revision
        artifact = db.scalar(
            select(RenderArtifact).where(
                RenderArtifact.project_id == project_id, RenderArtifact.revision == revision
            )
        )
        if artifact:
            movie = safe_path(settings.output_dir, artifact.path)
            if (
                movie.is_file()
                and digest(movie) == artifact.sha256
                and artifact.probe.get("checks")
                and all(artifact.probe["checks"].values())
            ):
                restored = "APPROVED" if project.approved_hash == artifact.sha256 else "HUMAN_REVIEW"
                checkpoint(job_id, owner, restored)
                return
        context = {
            "idea": project.idea,
            "channel": project.channel_id,
            "duration": project.target_duration,
            "series": None,
            "characters": [],
            "assets": [],
            "language": "en-US",
            "audience": "ages 3-7" if project.channel_id == "wondernest" else "older teens and adults",
        }
        if project.series_id:
            series = db.get(Series, project.series_id)
            context["series"] = {"name": series.name, "style": series.style}
            context["characters"] = [
                {"id": c.id, "name": c.name, "description": c.description, "expressions": c.expressions}
                for c in db.scalars(select(Character).where(Character.series_id == series.id))
            ]
        context["assets"] = [
            {"id": a.id, "name": a.name, "kind": a.kind} for a in db.scalars(select(SceneAsset))
        ]
        context["visual_medium"] = "2.5D geometric or imported transparent sprites; not physical 3D"
        saved = dict(job.checkpoint)
        selection, _ = job_selection(db, job)
    selection = validate_selection(selection)
    if saved.get("_ai_selection") != selection:
        checkpoint(job_id, owner, "SCRIPTING", "_ai_selection", selection)
        saved["_ai_selection"] = selection
    provider = get_provider(selection)

    def agent(role, response_type, stage):
        key = role.lower().replace(" ", "_")
        if key not in saved:
            checkpoint(job_id, owner, stage)
            event(project_id, stage, role + ": started")
            emitted = set()

            def progress(kind):
                if kind not in emitted:
                    emitted.add(kind)
                    event(project_id, stage, role + ": " + kind)

            result = provider.generate(
                role,
                context,
                response_type,
                cancel=cancel,
                emit=progress,
            )
            with provider.persistence_guard():
                sources = {**saved.get("_ai_step_sources", {}), key: selection}
                checkpoint(job_id, owner, stage, "_ai_step_sources", sources)
                saved["_ai_step_sources"] = sources
                saved[key] = result.model_dump(mode="json")
                checkpoint(job_id, owner, stage, key, saved[key])
                event(project_id, stage, role + ": completed")
        context[key] = saved[key]
        return response_type.model_validate(saved[key])

    agent("Creative Director", AgentResult, "SCRIPTING")
    with Session() as db:
        current = db.get(VideoProject, project_id)
        manual_script = current.script
        manual_board = current.storyboard
        manual_metadata = current.metadata_json
    script = (
        Script.model_validate(manual_script) if manual_script else agent("Script Writer", Script, "SCRIPTING")
    )
    context["script"] = script.model_dump(mode="json")
    with Session.begin() as db:
        current = db.get(VideoProject, project_id)
        if current.revision != revision:
            from .security import Cancelled

            raise Cancelled("Project changed")
        current.script = script.model_dump(mode="json")
        current.title, current.description = script.title, script.description
        if not db.scalar(
            select(ScriptVersion.id).where(
                ScriptVersion.project_id == project_id, ScriptVersion.revision == revision
            )
        ):
            db.add(ScriptVersion(project_id=project_id, revision=revision, content=current.script))
    board = (
        Board.model_validate(manual_board)
        if manual_board
        else agent("Storyboard Planner", Board, "STORYBOARDING")
    )
    total = sum(s.duration for s in board.scenes)
    if abs(total - context["duration"]) > 1:
        raise ValueError(f"Storyboard duration {total:.1f}s differs from target {context['duration']}s")
    context["board"] = board.model_dump(mode="json")
    with Session.begin() as db:
        current = db.get(VideoProject, project_id)
        current.storyboard = context["board"]
        db.execute(delete(VideoScene).where(VideoScene.project_id == project_id))
        start = 0
        for scene in board.scenes:
            db.add(
                VideoScene(
                    project_id=project_id,
                    start_time=start,
                    duration=scene.duration,
                    background=scene.background,
                    narration=scene.narration,
                    animation_commands=[x.model_dump(mode="json") for x in scene.layers],
                    camera_commands=scene.camera.model_dump(),
                    transition=scene.transition,
                )
            )
            start += scene.duration
        if not db.scalar(
            select(Storyboard.id).where(Storyboard.project_id == project_id, Storyboard.revision == revision)
        ):
            db.add(Storyboard(project_id=project_id, revision=revision, content=current.storyboard))
    agent("Visual Director", AgentResult, "ASSET_CHECK")
    agent("Animation Planner", AgentResult, "ASSET_CHECK")
    checkpoint(job_id, owner, "ASSET_CHECK")
    with Session() as db:
        asset_map = {a.id: safe_path(settings.assets_dir, a.path) for a in db.scalars(select(SceneAsset))}
    missing = [
        layer.asset_id
        for s in board.scenes
        for layer in s.layers
        if layer.kind == "image"
        and layer.essential
        and (layer.asset_id not in asset_map or not asset_map[layer.asset_id].is_file())
    ]
    missing += [
        entry.asset_id
        for scene in board.scenes
        for layer in scene.layers
        for entry in layer.expression_assets
        if layer.essential and (entry.asset_id not in asset_map or not asset_map[entry.asset_id].is_file())
    ]
    if missing:
        checkpoint(job_id, owner, "WAITING_FOR_ASSETS", "asset_requests", missing)
        raise ConfigurationRequired("Missing essential image assets: " + ", ".join(missing))
    reviewer = agent("Quality Reviewer", AgentResult, "ASSET_CHECK")
    checkpoint(job_id, owner, "AUDIO_GENERATION")
    folder = settings.output_dir / project_id / str(revision)
    folder.mkdir(parents=True, exist_ok=True)
    with Session() as db:
        narration = db.get(VideoProject, project_id).narration
    if narration.get("path"):
        audio = safe_path(settings.storage_root, narration["path"])
        measured = float(probe(audio)["format"]["duration"])
        if abs(measured - total) > 1:
            raise ConfigurationRequired("Imported narration duration must match storyboard (within 1s)")
    else:
        audio = Piper().scenes(board, folder / "audio", cancel=cancel)
    if narration.get("mix"):
        mix = AudioMix.model_validate(narration["mix"])
        audio = mix_tracks(audio, folder / "mixed.wav", total, mix, asset_map)
    checkpoint(job_id, owner, "AUDIO_GENERATION", "audio", str(audio))
    metadata = (
        Metadata.model_validate(manual_metadata)
        if manual_metadata
        else agent("Publishing Assistant", Metadata, "AUDIO_GENERATION")
    )
    with Session.begin() as db:
        current = db.get(VideoProject, project_id)
        current.metadata_json = metadata.model_dump()
        current.narration = {**current.narration, "generated_path": str(audio)}
    checkpoint(job_id, owner, "RENDERING")
    movie = folder / "video.mp4"
    started = time.monotonic()
    render(
        board,
        movie,
        width=project.width,
        height=project.height,
        fps=project.fps,
        audio=audio,
        assets=asset_map,
        cancel=cancel,
        progress=lambda n: event(project_id, "RENDERING", f"{n}%"),
    )
    seconds = time.monotonic() - started
    checkpoint(job_id, owner, "TECHNICAL_VALIDATION")
    validation = validate_video(movie, project.width, project.height, project.fps, total)
    validation["review_flags"] = reviewer.flags + (
        ["Scientific claims and source evidence require human verification"]
        if project.channel_id == "how-it-works"
        else []
    )
    validation["scientific_sources"] = [s.model_dump() for s in script.sources]
    validation["scientific_verification"] = (
        "Human source verification required" if project.channel_id == "how-it-works" else "Not applicable"
    )
    from .render import frame

    frame(
        board.scenes[0], min(0.5, board.scenes[0].duration / 2), project.width, project.height, asset_map
    ).save(folder / "thumbnail.png")
    (folder / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    (folder / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    # Time-aligned captions are based on scene boundaries, not guessed word timestamps.
    def stamp(t):
        ms = round(t * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    captions, start = [], 0
    for i, scene in enumerate(board.scenes):
        captions.append(f"{i + 1}\n{stamp(start)} --> {stamp(start + scene.duration)}\n{scene.narration}\n")
        start += scene.duration
    (folder / "captions.srt").write_text("\n".join(captions), encoding="utf-8")
    with Session.begin() as db:
        db.add(
            RenderArtifact(
                project_id=project_id,
                revision=revision,
                path=str(movie.relative_to(settings.output_dir)),
                sha256=digest(movie),
                probe=validation,
                render_seconds=seconds,
            )
        )
    checkpoint(job_id, owner, "HUMAN_REVIEW")
