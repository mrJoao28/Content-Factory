"""Apply explicit music events to supported Blender actions, rejecting overlaps."""
import array
import hashlib
import json
import sys
import wave

from .music import take_path
from .music_schema import MusicPlan
from .visual_schema import VisualBoard


def energy_markers(path):
    """Audio-energy approximation, not phonetic alignment; persisted as editable mouth times."""
    times = []
    with wave.open(str(path), 'rb') as source:
        rate, frame = source.getframerate(), 0
        block = max(1, round(rate*.15))
        while data := source.readframes(block):
            values = array.array('h', data)
            if sys.byteorder != 'little':
                values.byteswap()
            if values and sum(v*v for v in values)/len(values) > 300**2:
                times.append(frame/rate)
            frame += len(values)
    return times


def synchronize(project, board):
    plan = MusicPlan.model_validate(project.music_plan)
    data = board.model_dump(mode='json')
    # AI does not invent singing mouth motion; only a measured selected take drives it.
    for shot in data['scenes']:
        shot['singing'] = []
    global_start = 0.0
    for segment in plan.segments:
        event_list = segment.events
        takes = project.music_state.get('takes', {}).get(segment.id, {})
        vocal = takes.get('vocals') or takes.get('premixed')
        mouth = (segment.mouth_times if segment.mouth_times is not None else energy_markers(take_path(vocal))) if segment.kind == 'song' and segment.singer == 'character' and vocal else []
        shot_start = 0.0
        for shot in data['scenes']:
            shot_end = shot_start+shot['duration']
            actors = {a['character_id'] for a in shot['characters']}
            for event in event_list:
                start, end = max(shot_start, global_start+event.time), min(shot_end, global_start+event.end)
                if start >= end:
                    continue
                if event.character_id not in actors:
                    raise ValueError('Musical action actor missing from the corresponding shot; revise storyboard')
                local_start, local_end = start-shot_start, end-shot_start
                # Explicit music events are authoritative. Conflicting planner actions must be repaired explicitly.
                existing = shot['actions']
                matching = [a for a in existing if a['character_id'] == event.character_id
                            and a['kind'] == event.action and abs(a['start']-local_start) < .001
                            and abs(a['end']-local_end) < .001]
                if not matching:
                    if any(a['character_id'] == event.character_id and a['start'] < local_end
                           and a['end'] > local_start for a in existing):
                        raise ValueError('Storyboard action conflicts with a music event; edit or regenerate storyboard')
                    existing.append(dict(character_id=event.character_id, kind=event.action,
                                         start=local_start, end=local_end, bpm=segment.bpm_requested))
                    existing.sort(key=lambda a: a['start'])
            selected = [global_start+t-shot_start for t in mouth
                        if shot_start <= global_start+t < shot_end]
            if selected:
                if segment.character_id not in actors:
                    raise ValueError('Visible singer missing from the shot; select offscreen singing or revise the scene')
                # Dialogue schema bounds each mouth list. Split into bounded cue records.
                for i in range(0, len(selected), 40):
                    shot['singing'].append(dict(character_id=segment.character_id, start=selected[i],
                        text='Manual singing cues' if segment.mouth_times is not None else 'Audio-energy approximation, not phonetic alignment',
                        mouth_times=selected[i:i+40]))
            shot_start = shot_end
        global_start += segment.duration
    return VisualBoard.model_validate(data).validate_project(project.target_duration, project.fps)


def plan_board(project_id, job_id, owner, provider, selection, context, saved, cancel):
    """Bounded per-segment AI requests and durable checkpoints for longer productions."""
    from .db import Session
    from .models import VideoProject
    from .queue import checkpoint, event
    from .storyboard_limits import validate_generated
    plan = MusicPlan.model_validate(context['music_plan'])
    cached = dict(saved.get('_music_boards', {}))
    scenes = []
    for segment in plan.segments:
        if cancel():
            from .security import Cancelled
            raise Cancelled('Musical storyboard cancelled; validated segments retained')
        local = {**context, 'duration': segment.duration, 'music_segment': segment.model_dump(),
                 'music_plan': {**plan.model_dump(), 'segments': [segment.model_dump()]},
                 'music_timeline': [r for r in context.get('music_timeline', []) if r['id'] == segment.id],
                 'previous_scene': scenes[-1].model_dump() if scenes else None,
                 'instructions': 'Plan ONLY this segment; scene times are local. Respect exact duration. '
                 'Music events are inserted by the application; leave those actor intervals free of other actions. '
                 'Preserve preceding character position/orientation/props unless the story explicitly changes them. '
                 'Use a maximum of 24 actions per scene; no invented assets or commands.'}
        identity = hashlib.sha256(json.dumps({'segment': segment.model_dump(exclude={
            'gain', 'instrumental_gain', 'effects_gain', 'fade_in', 'fade_out', 'ducking'}),
            'cast': plan.characters, 'environment': plan.environment, 'selection': selection,
            'previous_scene': local['previous_scene']}, sort_keys=True).encode()).hexdigest()
        item = cached.get(segment.id, {})
        if item.get('input_hash') == identity:
            board = VisualBoard.model_validate(item['board'])
            validate_generated(board, local)
        else:
            event(project_id, 'STORYBOARDING', f'Musical storyboard {segment.id}: started')
            from types import SimpleNamespace
            for attempt in range(2):
                board = provider.generate('Storyboard Planner', local, VisualBoard, cancel=cancel,
                                          emit=lambda _: None)
                try:
                    validate_generated(board, local)
                    with Session() as db:
                        current = db.get(VideoProject, project_id)
                        preview = SimpleNamespace(music_plan={**plan.model_dump(), 'segments': [segment.model_dump()]},
                            music_state=current.music_state, target_duration=segment.duration, fps=current.fps)
                        synchronize(preview, board)
                    break
                except ValueError as exc:
                    if attempt:
                        raise
                    local['planning_repair'] = str(exc)[:2000]
                    event(project_id, 'STORYBOARDING', f'Musical storyboard {segment.id}: one validation repair requested')
            with provider.persistence_guard():
                cached[segment.id] = {'input_hash': identity, 'board': board.model_dump(mode='json'),
                                      'text_selection': selection}
                checkpoint(job_id, owner, 'STORYBOARDING', '_music_boards', cached)
            event(project_id, 'STORYBOARDING', f'Musical storyboard {segment.id}: validated and completed')
        scenes.extend(board.scenes)
    return VisualBoard(duration=context['duration'], scenes=scenes)
