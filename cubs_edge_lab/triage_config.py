"""Fixed November free-agent pool triage design configuration."""

COHORT_YEARS = (2018, 2019, 2021, 2022, 2023, 2024, 2025)
TRAIN_YEARS = (2018, 2019, 2021, 2022, 2023)
VALIDATION_YEAR = 2024
HOLDOUT_YEAR = 2025
SPORT_IDS = (1, 11, 12, 13, 14)
STAT_YEARS = tuple(range(2017, 2026))
TOP_K = (25, 50, 100)
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = 43017
L2_GRID = (0.01, 0.1, 1.0, 10.0)
PRIMARY_K_CANDIDATES = (25, 50, 100)
# Frozen before measuring the Cubs transaction counts.
MINOR_CONTRACT_PATTERN = r"\bminor[ -]league contract\b"
INVITATION_PATTERN = (
    r"\b(?:non[ -]roster invit\w*|spring training invit\w*|"
    r"invit\w*(?:\s+\w+){0,5}\s+(?:to\s+)?"
    r"(?:spring training|camp))"
)
OTHER_SIGNING_PATTERN = r"\b(?:signed|signs|signing)\b"
