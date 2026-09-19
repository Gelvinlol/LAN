"""Backward-compatible import for the application's single scheduler."""

from simple_scheduler import SimpleScheduler


class DutyScheduler(SimpleScheduler):
    pass
