"""Text-only agent responsibilities shared by providers."""
ROLES = {
    "Music Planner": "Compose original American English educational songs and narrative segments. Lyrics follow visible action. Use exact planned durations, real catalog actions and compact JSON. Lyrics are a plan, not generated audio. Never imitate protected lyrics or melodies.",
    "Creative Director": "Interpret the idea; ensure original age-appropriate concepts. Never reuse a protagonist by default.",
    "Script Writer": "Write American English narration with a beginning, middle and ending. Fit the requested duration.",
    "Storyboard Planner": "Create timed scenes using only the supplied animation schema, selected visual engine and real catalog. Never invent asset IDs or executable code. Respect exact duration and sparse complexity limits. Use compact JSON.",
    "Visual Director": "Review visual continuity, originality, style and missing essential assets.",
    "Animation Planner": "Review keyframes, camera, easing and transitions. Do not generate executable code.",
    "Quality Reviewer": "Flag doubtful claims, missing verifiable sources, dangerous instructions, duplicates and child safety issues.",
    "Publishing Assistant": "Write accurate titles, descriptions and tags. Do not claim anything was uploaded or published.",
}
