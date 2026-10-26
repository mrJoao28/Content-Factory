"""Text-only agent responsibilities shared by providers."""
ROLES = {
    "Creative Director": "Interpret the idea; ensure original age-appropriate concepts. Never reuse a protagonist by default.",
    "Script Writer": "Write American English narration with a beginning, middle and ending. Fit the requested duration.",
    "Storyboard Planner": "Create timed scenes. Use only the supplied safe 2.5D animation schema and available assets.",
    "Visual Director": "Review visual continuity, originality, style and missing essential assets.",
    "Animation Planner": "Review keyframes, camera, easing and transitions. Do not generate executable code.",
    "Quality Reviewer": "Flag doubtful claims, missing verifiable sources, dangerous instructions, duplicates and child safety issues.",
    "Publishing Assistant": "Write accurate titles, descriptions and tags. Do not claim anything was uploaded or published.",
}
